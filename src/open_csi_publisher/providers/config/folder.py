from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loguru import logger

from open_csi_publisher.providers.base import ConfigProvider


class DatasetConfigNotFoundError(LookupError):
    pass


class FolderConfigProvider(ConfigProvider):
    """Scans a folder of `<dataset_id>.json` files (implementation_plan.md §4.3).
    Dataset identity is the filename stem, not a field re-read from each file's
    content, so listing datasets never requires parsing/validating every config."""

    def __init__(self, folder: Path):
        self._folder = Path(folder)

    def list_dataset_ids(self) -> list[str]:
        return sorted(p.stem for p in self._folder.glob("*.json"))

    def load_config(self, dataset_id: str) -> dict[str, Any]:
        path = self._path_for(dataset_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.error("failed to parse {} as JSON", path)
            raise

    def config_hash(self, dataset_id: str) -> str:
        return hashlib.sha256(self._path_for(dataset_id).read_bytes()).hexdigest()

    def _path_for(self, dataset_id: str) -> Path:
        path = self._folder / f"{dataset_id}.json"
        if not path.is_file():
            raise DatasetConfigNotFoundError(dataset_id)
        return path
