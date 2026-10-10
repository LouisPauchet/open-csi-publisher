"""Read-only storage abstraction: local folders and S3 buckets."""

from pathlib import Path

import fsspec
import pytest

from open_csi_publisher.storage import (
    READ_ONLY_API,
    LocalStorage,
    S3Storage,
    StorageConfigError,
    make_storage,
)

WRITE_NAMES = {"put", "write", "rm", "remove", "delete", "mkdir", "touch", "pipe", "mv", "copy",
               "open_write", "write_text", "write_bytes", "fs"}


@pytest.fixture
def local_tree(tmp_path: Path) -> Path:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.dat").write_text("alpha")
    (tmp_path / "sub" / "b.dat").write_text("bravo!")
    (tmp_path / "c.json").write_text("{}")
    return tmp_path


@pytest.fixture
def memory_s3(monkeypatch) -> S3Storage:
    fs = fsspec.filesystem("memory")
    fs.store.clear()
    fs.pseudo_dirs[:] = [""]
    fs.pipe_file("/bkt/data/a.dat", b"alpha")
    fs.pipe_file("/bkt/data/sub/b.dat", b"bravo!")
    fs.pipe_file("/bkt/data/c.json", b"{}")
    return S3Storage(fs=fs, bucket="bkt", prefix="data")


def _both(request, name):
    return request.getfixturevalue(name)


@pytest.fixture(params=["local", "s3"])
def storage(request, local_tree, memory_s3):
    return LocalStorage(local_tree) if request.param == "local" else memory_s3


def test_glob_returns_relative_posix_paths(storage):
    assert sorted(storage.glob("*.dat")) == ["a.dat"]
    assert sorted(storage.glob("**/*.dat")) == ["a.dat", "sub/b.dat"]


def test_stat_returns_size(storage):
    assert storage.stat("sub/b.dat").size == 6


def test_read_text_and_bytes(storage):
    assert storage.read_text("a.dat") == "alpha"
    assert storage.read_bytes("a.dat") == b"alpha"


def test_open_read_is_binary_and_readonly(storage):
    with storage.open_read("a.dat") as fh:
        assert fh.read() == b"alpha"


def test_is_file(storage):
    assert storage.is_file("a.dat")
    assert not storage.is_file("missing.dat")
    assert not storage.is_file("sub")


@pytest.mark.parametrize("cls", [LocalStorage, S3Storage])
def test_public_surface_is_exactly_read_only_allowlist(cls):
    public = {n for n in dir(cls) if not n.startswith("_")}
    assert public == set(READ_ONLY_API)
    assert not (public & WRITE_NAMES)


def test_s3_storage_does_not_expose_filesystem(memory_s3):
    assert not hasattr(memory_s3, "fs")
    assert not hasattr(memory_s3, "filesystem")


def test_s3_run_leaves_bucket_unchanged(memory_s3):
    fs = fsspec.filesystem("memory")
    before = {k: fs.cat_file(k) for k in fs.find("/bkt")}
    memory_s3.glob("**/*")
    memory_s3.read_bytes("a.dat")
    memory_s3.stat("a.dat")
    assert {k: fs.cat_file(k) for k in fs.find("/bkt")} == before


def test_s3_open_read_rejects_path_escape(memory_s3):
    with pytest.raises(ValueError):
        memory_s3.read_bytes("../other/x")


# --- make_storage ---

def test_make_storage_local(tmp_path):
    s = make_storage("mount/data", base_dir=tmp_path, env_prefix=None)
    assert isinstance(s, LocalStorage)


def test_make_storage_s3_bucket_from_env(monkeypatch, tmp_path):
    for k, v in {"ACCESS_KEY_ID": "k", "SECRET_ACCESS_KEY": "s",
                 "ENDPOINT": "http://localhost:9", "REGION": "r", "BUCKET": "envbkt"}.items():
        monkeypatch.setenv(f"LN_OFS_S3_{k}", v)
    s = make_storage("s3:///__config__/", base_dir=tmp_path, env_prefix="LN_OFS_S3")
    assert isinstance(s, S3Storage)
    assert s.bucket == "envbkt" and s.prefix == "__config__"


def test_make_storage_s3_url_bucket_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("LN_OFS_S3_BUCKET", "envbkt")
    monkeypatch.setenv("LN_OFS_S3_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("LN_OFS_S3_SECRET_ACCESS_KEY", "s")
    monkeypatch.setenv("LN_OFS_S3_ENDPOINT", "http://localhost:9")
    s = make_storage("s3://urlbkt/data", base_dir=tmp_path, env_prefix="LN_OFS_S3")
    assert s.bucket == "urlbkt" and s.prefix == "data"


def test_make_storage_s3_missing_credentials_raises_config_error(monkeypatch, tmp_path):
    for k in ("ACCESS_KEY_ID", "SECRET_ACCESS_KEY", "ENDPOINT", "REGION", "BUCKET"):
        monkeypatch.delenv(f"LN_OFS_S3_{k}", raising=False)
    with pytest.raises(StorageConfigError, match="LN_OFS_S3_ACCESS_KEY_ID"):
        make_storage("s3://b/x", base_dir=tmp_path, env_prefix="LN_OFS_S3")


def test_make_storage_s3_without_prefix_raises(tmp_path):
    with pytest.raises(StorageConfigError):
        make_storage("s3://b/x", base_dir=tmp_path, env_prefix=None)


def test_make_storage_s3_no_bucket_anywhere_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("LN_OFS_S3_BUCKET", raising=False)
    monkeypatch.setenv("LN_OFS_S3_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("LN_OFS_S3_SECRET_ACCESS_KEY", "s")
    with pytest.raises(StorageConfigError, match="LN_OFS_S3_BUCKET"):
        make_storage("s3:///data", base_dir=tmp_path, env_prefix="LN_OFS_S3")


def test_describe_gives_human_readable_location(local_tree, memory_s3):
    assert LocalStorage(local_tree).describe("a.dat") == str(local_tree / "a.dat")
    assert memory_s3.describe("sub/b.dat") == "s3://bkt/data/sub/b.dat"
