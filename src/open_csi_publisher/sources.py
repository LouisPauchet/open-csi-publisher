from __future__ import annotations

import os
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
    """One entry from the top-level sources.yaml (implementation_plan.md §4.1).

    `credentials_env_prefix` is only meaningful for `type: thingsboard` (unlike
    `config_location`/`data_location`, ignored there) — it names which env vars
    hold that source's ThingsBoard credentials: `{prefix}_BASE_URL` plus either
    `{prefix}_API_KEY` or `{prefix}_USERNAME`/`{prefix}_PASSWORD` (API key takes
    precedence if both are set), so multiple thingsboard sources can each point
    at a different tenant. Defaults to "THINGSBOARD" so a single-tenant
    sources.yaml entry doesn't need to set it at all.
    """

    id: str
    type: str
    config_provider: str
    config_location: str
    data_location: str
    credentials_env_prefix: str = "THINGSBOARD"


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


@lru_cache(maxsize=None)
def _get_thingsboard_client(credentials_env_prefix: str) -> ThingsBoardClient:
    """One client per credentials_env_prefix for the process lifetime, not one
    per request (unlike the other providers below, which are cheap Path
    wrappers reconstructed on every call) — so login happens once per
    ThingsBoard tenant, shared by both the config and data provider instances
    for every source entry that names the same prefix. Cached separately per
    prefix (rather than a single `maxsize=1` singleton) so multiple
    `thingsboard` sources, each pointing at a different tenant, each get their
    own client/session.

    Credentials are read directly from the environment (not through
    `Settings`) because the set of valid prefixes is open-ended — defined by
    whatever `sources.yaml` entries exist, not a fixed set of settings fields.

    Either `{prefix}_API_KEY` or `{prefix}_USERNAME`/`{prefix}_PASSWORD` may be
    set; the API key takes precedence if both are present.
    """
    base_url = os.environ.get(f"{credentials_env_prefix}_BASE_URL")
    api_key = os.environ.get(f"{credentials_env_prefix}_API_KEY")
    username = os.environ.get(f"{credentials_env_prefix}_USERNAME")
    password = os.environ.get(f"{credentials_env_prefix}_PASSWORD")
    if not base_url or not (api_key or (username and password)):
        raise RuntimeError(
            f"a 'thingsboard' source is configured with credentials_env_prefix="
            f"{credentials_env_prefix!r} but {credentials_env_prefix}_BASE_URL and "
            f"either {credentials_env_prefix}_API_KEY or "
            f"{credentials_env_prefix}_USERNAME/{credentials_env_prefix}_PASSWORD "
            "are not set"
        )
    if api_key:
        return ThingsBoardClient(
            base_url,
            api_key=api_key,
            discovery_ttl_seconds=settings.thingsboard_discovery_interval_seconds,
        )
    return ThingsBoardClient(
        base_url,
        username,
        password,
        discovery_ttl_seconds=settings.thingsboard_discovery_interval_seconds,
    )


def get_config_provider(source: SourceEntry, *, base_dir: Path) -> ConfigProvider:
    if source.config_provider == "folder":
        return FolderConfigProvider(base_dir / source.config_location)
    if source.config_provider == "thingsboard":
        return ThingsBoardConfigProvider(_get_thingsboard_client(source.credentials_env_prefix))
    raise ValueError(f"unknown config_provider: {source.config_provider!r}")


def get_data_provider(source: SourceEntry, *, base_dir: Path) -> DataProvider:
    if source.type == "loggernet":
        return LoggerNetDataProvider(base_dir / source.data_location)
    if source.type == "generic_csv":
        return GenericCsvDataProvider(base_dir / source.data_location)
    if source.type == "thingsboard":
        return ThingsBoardDataProvider(_get_thingsboard_client(source.credentials_env_prefix))
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
