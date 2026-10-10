from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from loguru import logger

from open_csi_publisher.providers.base import ConfigProvider
from open_csi_publisher.storage import LocalStorage, Storage


class DatasetConfigNotFoundError(LookupError):
    pass


class FolderConfigProvider(ConfigProvider):
    """Scans a folder of `<dataset_id>.json` files (implementation_plan.md §4.3).
    Dataset identity is the filename stem, not a field re-read from each file's
    content, so listing datasets never requires parsing/validating every config."""

    def __init__(self, folder: Path | Storage):
        self._storage: Storage = (
            folder if not isinstance(folder, (str, Path)) else LocalStorage(Path(folder))
        )

    def list_dataset_ids(self) -> list[str]:
        return sorted(PurePosixPath(p).stem for p in self._storage.glob("*.json"))

    def load_config(self, dataset_id: str) -> dict[str, Any]:
        rel = self._rel_for(dataset_id)
        try:
            return json.loads(self._storage.read_text(rel))
        except json.JSONDecodeError:
            logger.error("failed to parse {} as JSON", self._storage.describe(rel))
            raise

    def config_hash(self, dataset_id: str) -> str:
        return hashlib.sha256(self._storage.read_bytes(self._rel_for(dataset_id))).hexdigest()

    def _rel_for(self, dataset_id: str) -> str:
        rel = f"{dataset_id}.json"
        if not self._storage.is_file(rel):
            raise DatasetConfigNotFoundError(dataset_id)
        return rel
