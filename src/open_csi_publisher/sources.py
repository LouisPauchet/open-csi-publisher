from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from open_csi_publisher.providers.base import ConfigProvider, DataProvider
from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.providers.config.thingsboard import ThingsBoardConfigProvider
from open_csi_publisher.providers.data.generic_csv.provider import GenericCsvDataProvider
from open_csi_publisher.providers.data.loggernet.provider import LoggerNetDataProvider
from open_csi_publisher.providers.data.thingsboard.provider import ThingsBoardDataProvider
from open_csi_publisher.providers.thingsboard_client import ThingsBoardClient
from open_csi_publisher.settings import settings


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


@lru_cache(maxsize=1)
def _get_thingsboard_client() -> ThingsBoardClient:
    """One client for the process lifetime, not one per request (unlike the
    other providers below, which are cheap Path wrappers reconstructed on
    every call) — so login happens once, shared by both the config and data
    provider instances for the (single, per "no multiple deployments for
    ThingsBoard") thingsboard source entry."""
    if not (settings.thingsboard_base_url and settings.thingsboard_username and settings.thingsboard_password):
        raise RuntimeError(
            "a 'thingsboard' source is configured but THINGSBOARD_BASE_URL/"
            "THINGSBOARD_USERNAME/THINGSBOARD_PASSWORD are not set"
        )
    return ThingsBoardClient(
        settings.thingsboard_base_url,
        settings.thingsboard_username,
        settings.thingsboard_password,
        discovery_ttl_seconds=settings.thingsboard_discovery_interval_seconds,
    )


def get_config_provider(source: SourceEntry, *, base_dir: Path) -> ConfigProvider:
    if source.config_provider == "folder":
        return FolderConfigProvider(base_dir / source.config_location)
    if source.config_provider == "thingsboard":
        return ThingsBoardConfigProvider(_get_thingsboard_client())
    raise ValueError(f"unknown config_provider: {source.config_provider!r}")


def get_data_provider(source: SourceEntry, *, base_dir: Path) -> DataProvider:
    if source.type == "loggernet":
        return LoggerNetDataProvider(base_dir / source.data_location)
    if source.type == "generic_csv":
        return GenericCsvDataProvider(base_dir / source.data_location)
    if source.type == "thingsboard":
        return ThingsBoardDataProvider(_get_thingsboard_client())
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
