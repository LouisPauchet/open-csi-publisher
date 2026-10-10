"""Read-only storage backends (local folder or S3 bucket).

SAFEGUARD: OpenCSIPublisher must never write to the data store. The classes here
expose only the methods listed in ``READ_ONLY_API``; the underlying s3fs
filesystem is private and every file is opened with a hard-coded ``"rb"`` mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Any, Protocol
from urllib.parse import urlparse

READ_ONLY_API = ("glob", "stat", "open_read", "read_text", "read_bytes", "is_file", "describe")


class StorageConfigError(ValueError):
    """Invalid or incomplete storage configuration."""


@dataclass(frozen=True)
class StatResult:
    size: int
    token: str  # change token: ETag for S3, mtime_ns for local files


class Storage(Protocol):
    def glob(self, pattern: str) -> list[str]: ...
    def stat(self, rel: str) -> StatResult: ...
    def open_read(self, rel: str) -> IO[bytes]: ...
    def read_text(self, rel: str, encoding: str = "utf-8") -> str: ...
    def read_bytes(self, rel: str) -> bytes: ...
    def is_file(self, rel: str) -> bool: ...
    def describe(self, rel: str) -> str: ...


def _check_rel(rel: str) -> str:
    parts = PurePosixPath(rel).parts
    if ".." in parts or PurePosixPath(rel).is_absolute():
        raise ValueError(f"Path escapes storage root: {rel!r}")
    return "/".join(parts)


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _abs(self, rel: str) -> Path:
        return self.root / _check_rel(rel)

    def glob(self, pattern: str) -> list[str]:
        return sorted(
            p.relative_to(self.root).as_posix() for p in self.root.glob(pattern) if p.is_file()
        )

    def stat(self, rel: str) -> StatResult:
        st = self._abs(rel).stat()
        return StatResult(size=st.st_size, token=str(st.st_mtime_ns))

    def open_read(self, rel: str) -> IO[bytes]:
        return open(self._abs(rel), "rb")

    def read_text(self, rel: str, encoding: str = "utf-8") -> str:
        return self._abs(rel).read_text(encoding=encoding)

    def read_bytes(self, rel: str) -> bytes:
        return self._abs(rel).read_bytes()

    def is_file(self, rel: str) -> bool:
        return self._abs(rel).is_file()

    def describe(self, rel: str) -> str:
        return str(self._abs(rel))


class S3Storage:
    """Read-only view of ``s3://bucket/prefix``. Relative keys match a mounted volume."""

    def __init__(self, fs: Any, bucket: str, prefix: str = "") -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.__fs = fs  # name-mangled: not part of the public surface

    def _key(self, rel: str) -> str:
        rel = _check_rel(rel) if rel else ""
        return "/".join(p for p in (self.bucket, self.prefix, rel) if p)

    def _strip(self, full: str) -> str:
        base = self._key("")
        full = full.lstrip("/")
        return full[len(base):].lstrip("/")

    def glob(self, pattern: str) -> list[str]:
        fs = self.__fs
        hits = fs.glob(self._key(pattern))
        return sorted(self._strip(h) for h in hits if fs.isfile(h))

    def stat(self, rel: str) -> StatResult:
        info = self.__fs.info(self._key(rel))
        token = str(info.get("ETag") or info.get("LastModified") or info.get("mtime") or "")
        return StatResult(size=int(info["size"]), token=token)

    def open_read(self, rel: str) -> IO[bytes]:
        return self.__fs.open(self._key(rel), "rb")

    def read_text(self, rel: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(rel).decode(encoding)

    def read_bytes(self, rel: str) -> bytes:
        return self.__fs.cat_file(self._key(rel))

    def is_file(self, rel: str) -> bool:
        return bool(self.__fs.isfile(self._key(rel)))

    def describe(self, rel: str) -> str:
        return "s3://" + self._key(rel)


def make_storage(location: str, base_dir: Path, env_prefix: str | None) -> Storage:
    """Build a storage for ``location``.

    ``s3://bucket/prefix`` uses that bucket; ``s3:///prefix`` (empty host) takes the
    bucket from ``<env_prefix>BUCKET``. Anything else is a local path under ``base_dir``.
    """
    if not location.startswith("s3://"):
        return LocalStorage(base_dir / location)

    if not env_prefix:
        raise StorageConfigError(
            f"S3 location {location!r} needs credentials_env_prefix (e.g. 'LN_OFS_S3_')"
        )
    url = urlparse(location)
    env = {
        name: os.environ.get(f"{env_prefix}{name}", "")
        for name in (
            "ACCESS_KEY_ID", "SECRET_ACCESS_KEY", "ENDPOINT", "REGION", "BUCKET",
            "ADDRESSING_STYLE",
        )
    }
    bucket = url.netloc or env["BUCKET"]
    missing = [f"{env_prefix}{n}" for n in ("ACCESS_KEY_ID", "SECRET_ACCESS_KEY") if not env[n]]
    if not bucket:
        missing.append(f"{env_prefix}BUCKET")
    if missing:
        raise StorageConfigError("Missing S3 configuration: " + ", ".join(missing))

    try:
        import s3fs
    except ImportError as exc:
        raise StorageConfigError(
            "S3 support requires the 's3' extra (pip install open-csi-publisher[s3])"
        ) from exc

    fs = s3fs.S3FileSystem(
        key=env["ACCESS_KEY_ID"],
        secret=env["SECRET_ACCESS_KEY"],
        endpoint_url=env["ENDPOINT"] or None,
        client_kwargs={"region_name": env["REGION"]} if env["REGION"] else {},
        config_kwargs={"s3": {"addressing_style": env["ADDRESSING_STYLE"] or "path"}},
        use_listings_cache=False,
    )
    return S3Storage(fs=fs, bucket=bucket, prefix=url.path)
