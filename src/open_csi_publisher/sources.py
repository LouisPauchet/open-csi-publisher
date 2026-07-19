from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from open_csi_publisher.providers.base import ConfigProvider, DataProvider
from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.providers.data.loggernet.provider import LoggerNetDataProvider


@dataclass(frozen=True)
class SourceEntry:
    """One entry from the top-level sources.yaml (implementation_plan.md §4.1)."""

    id: str
    type: str
    config_provider: str
    config_location: str
    data_location: str


@dataclass(frozen=True)
class DatasetLocation:
    """A dataset resolved to its source and the providers needed to build it."""

    source_id: str
    dataset_id: str
    config_provider: ConfigProvider
    data_provider: DataProvider


def load_sources(path: Path) -> list[SourceEntry]:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [SourceEntry(**entry) for entry in doc["sources"]]


def get_config_provider(source: SourceEntry, *, base_dir: Path) -> ConfigProvider:
    if source.config_provider == "folder":
        return FolderConfigProvider(base_dir / source.config_location)
    raise ValueError(f"unknown config_provider: {source.config_provider!r}")


def get_data_provider(source: SourceEntry, *, base_dir: Path) -> DataProvider:
    if source.type == "loggernet":
        return LoggerNetDataProvider(base_dir / source.data_location)
    raise ValueError(f"unknown source type: {source.type!r}")


def list_all_datasets(sources: list[SourceEntry], *, base_dir: Path) -> list[DatasetLocation]:
    """Every dataset across every configured source, each paired with the
    providers needed to build it — the enumeration the listing/search service
    (and, later, the rest of the REST API) iterates over."""
    locations: list[DatasetLocation] = []
    for source in sources:
        config_provider = get_config_provider(source, base_dir=base_dir)
        data_provider = get_data_provider(source, base_dir=base_dir)
        for dataset_id in config_provider.list_dataset_ids():
            locations.append(DatasetLocation(source.id, dataset_id, config_provider, data_provider))
    return locations
