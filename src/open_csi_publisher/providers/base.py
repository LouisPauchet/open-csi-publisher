from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Sequence

import xarray as xr

from open_csi_publisher.core.models import FileRecord


class ConfigProvider(ABC):
    """Where/how dataset configs for a source are discovered (implementation_plan.md
    §4.3). Implementations: FolderConfigProvider (scans __config__/*.json), a future
    DatabaseConfigProvider, etc."""

    @abstractmethod
    def list_dataset_ids(self) -> list[str]: ...

    @abstractmethod
    def load_config(self, dataset_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def config_hash(self, dataset_id: str) -> str: ...


class DataProvider(ABC):
    """How actual readings are fetched and how new/active data is detected
    (implementation_plan.md §5.1). `get_file_index`/`read_range` take the
    caller-resolved `previous`/`files` list from the index service rather than
    rediscovering files themselves on every call — an explicit extension to the
    architecture doc's illustrative interface sketch, needed to make the lazy
    file-index refresh (§6) and core builder (§7) actually implementable."""

    @abstractmethod
    def get_file_index(
        self, source_config: dict[str, Any], previous: Sequence[FileRecord] = ()
    ) -> list[FileRecord]: ...

    @abstractmethod
    def read_range(
        self,
        source_config: dict[str, Any],
        files: Sequence[FileRecord],
        start: datetime | None,
        end: datetime | None,
        variables: list[str] | None = None,
    ) -> xr.Dataset: ...
