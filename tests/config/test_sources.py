from __future__ import annotations

import pytest

from open_csi_publisher import sources as sources_module
from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.providers.config.thingsboard import ThingsBoardConfigProvider
from open_csi_publisher.providers.data.loggernet.provider import LoggerNetDataProvider
from open_csi_publisher.providers.data.thingsboard.provider import ThingsBoardDataProvider
from open_csi_publisher.settings import settings
from open_csi_publisher.sources import (
    SourceEntry,
    get_config_provider,
    get_data_provider,
    list_all_datasets,
    load_sources,
)

from ..conftest import REPO_ROOT, requires_mount


@pytest.fixture(autouse=True)
def _clear_thingsboard_client_cache():
    # _get_thingsboard_client is process-lifetime lru_cache'd (sources.py) —
    # any test that touches settings.thingsboard_* must clear it before and
    # after, or a stale cached client from one test leaks into the next.
    sources_module._get_thingsboard_client.cache_clear()
    yield
    sources_module._get_thingsboard_client.cache_clear()


def test_load_sources_parses_the_real_sources_yaml(sample_config_dir):
    sources = load_sources(sample_config_dir / "sources.yaml")
    assert sources == [
        SourceEntry(
            id="loggernet_test_server",
            type="loggernet",
            config_provider="folder",
            config_location="sample_configs/",
            data_location="mount/loggernet-test-server/",
        )
    ]


def test_get_config_provider_folder_lists_the_sample_datasets(sample_config_dir):
    source = SourceEntry(
        id="s", type="loggernet", config_provider="folder",
        config_location="sample_configs/", data_location="mount/loggernet-test-server/",
    )
    provider = get_config_provider(source, base_dir=REPO_ROOT)
    assert isinstance(provider, FolderConfigProvider)
    assert set(provider.list_dataset_ids()) == {
        "isfjord_radio_solar_park_measurements3",
        "kapp_thordsen_10minute",
        "hanna_resvoll_10min",
    }


def test_get_config_provider_unknown_provider_raises():
    source = SourceEntry(
        id="s", type="loggernet", config_provider="database",
        config_location="x", data_location="y",
    )
    with pytest.raises(ValueError):
        get_config_provider(source, base_dir=REPO_ROOT)


def test_get_data_provider_loggernet_returns_provider():
    source = SourceEntry(
        id="s", type="loggernet", config_provider="folder",
        config_location="sample_configs/", data_location="mount/loggernet-test-server/",
    )
    provider = get_data_provider(source, base_dir=REPO_ROOT)
    assert isinstance(provider, LoggerNetDataProvider)


def test_get_data_provider_unknown_type_raises():
    source = SourceEntry(
        id="s", type="some_future_type", config_provider="folder",
        config_location="x", data_location="y",
    )
    with pytest.raises(ValueError):
        get_data_provider(source, base_dir=REPO_ROOT)


def test_get_data_provider_generic_csv_returns_provider():
    from open_csi_publisher.providers.data.generic_csv.provider import GenericCsvDataProvider

    source = SourceEntry(
        id="s", type="generic_csv", config_provider="folder",
        config_location="x", data_location="tests/fixtures/generic_csv/data/",
    )
    provider = get_data_provider(source, base_dir=REPO_ROOT)
    assert isinstance(provider, GenericCsvDataProvider)


def test_get_thingsboard_client_raises_when_settings_unset(monkeypatch):
    monkeypatch.setattr(settings, "thingsboard_base_url", None)
    monkeypatch.setattr(settings, "thingsboard_username", None)
    monkeypatch.setattr(settings, "thingsboard_password", None)

    with pytest.raises(RuntimeError):
        sources_module._get_thingsboard_client()


def test_get_config_provider_and_get_data_provider_thingsboard_share_one_client(monkeypatch):
    monkeypatch.setattr(settings, "thingsboard_base_url", "http://tb.example.test")
    monkeypatch.setattr(settings, "thingsboard_username", "admin")
    monkeypatch.setattr(settings, "thingsboard_password", "secret")

    source = SourceEntry(
        id="s", type="thingsboard", config_provider="thingsboard",
        config_location="", data_location="",
    )
    config_provider = get_config_provider(source, base_dir=REPO_ROOT)
    data_provider = get_data_provider(source, base_dir=REPO_ROOT)

    assert isinstance(config_provider, ThingsBoardConfigProvider)
    assert isinstance(data_provider, ThingsBoardDataProvider)
    assert config_provider._client is data_provider._client


@requires_mount
def test_list_all_datasets_enumerates_across_sources(sample_config_dir):
    sources = load_sources(sample_config_dir / "sources.yaml")
    locations = list_all_datasets(sources, base_dir=REPO_ROOT)

    dataset_ids = {loc.dataset_id for loc in locations}
    assert dataset_ids == {
        "isfjord_radio_solar_park_measurements3",
        "kapp_thordsen_10minute",
        "hanna_resvoll_10min",
    }
    assert all(loc.source_id == "loggernet_test_server" for loc in locations)
