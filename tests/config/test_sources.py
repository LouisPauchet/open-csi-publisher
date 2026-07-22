from __future__ import annotations

import pytest

from open_csi_publisher import sources as sources_module
from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.providers.config.thingsboard import ThingsBoardConfigProvider
from open_csi_publisher.providers.data.loggernet.provider import LoggerNetDataProvider
from open_csi_publisher.providers.data.thingsboard.provider import ThingsBoardDataProvider
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
    # _get_thingsboard_client is process-lifetime lru_cache'd (sources.py),
    # keyed by credentials_env_prefix — any test that touches THINGSBOARD*
    # env vars must clear it before and after, or a stale cached client for
    # that prefix leaks into a later test.
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


def test_get_thingsboard_client_raises_when_env_vars_unset(monkeypatch):
    monkeypatch.delenv("THINGSBOARD_BASE_URL", raising=False)
    monkeypatch.delenv("THINGSBOARD_USERNAME", raising=False)
    monkeypatch.delenv("THINGSBOARD_PASSWORD", raising=False)

    with pytest.raises(RuntimeError):
        sources_module._get_thingsboard_client("THINGSBOARD")


def test_get_config_provider_and_get_data_provider_thingsboard_share_one_client(monkeypatch):
    monkeypatch.setenv("THINGSBOARD_BASE_URL", "http://tb.example.test")
    monkeypatch.setenv("THINGSBOARD_USERNAME", "admin")
    monkeypatch.setenv("THINGSBOARD_PASSWORD", "secret")

    # credentials_env_prefix omitted -> defaults to "THINGSBOARD", so a
    # sources.yaml written before multi-instance support keeps working
    # unchanged.
    source = SourceEntry(
        id="s", type="thingsboard", config_provider="thingsboard",
        config_location="", data_location="",
    )
    config_provider = get_config_provider(source, base_dir=REPO_ROOT)
    data_provider = get_data_provider(source, base_dir=REPO_ROOT)

    assert isinstance(config_provider, ThingsBoardConfigProvider)
    assert isinstance(data_provider, ThingsBoardDataProvider)
    assert config_provider._client is data_provider._client


def test_get_thingsboard_client_uses_api_key_when_set(monkeypatch):
    monkeypatch.setenv("THINGSBOARD_APIKEY_BASE_URL", "http://apikey.example.test")
    monkeypatch.setenv("THINGSBOARD_APIKEY_API_KEY", "tb_secret")

    captured = {}

    class RecordingClient:
        def __init__(
            self, base_url, username=None, password=None, *, api_key=None, discovery_ttl_seconds=3600
        ):
            captured["base_url"] = base_url
            captured["username"] = username
            captured["password"] = password
            captured["api_key"] = api_key

    monkeypatch.setattr(sources_module, "ThingsBoardClient", RecordingClient)

    sources_module._get_thingsboard_client("THINGSBOARD_APIKEY")

    assert captured == {
        "base_url": "http://apikey.example.test",
        "username": None,
        "password": None,
        "api_key": "tb_secret",
    }


def test_get_thingsboard_client_api_key_takes_precedence_over_credentials(monkeypatch):
    monkeypatch.setenv("THINGSBOARD_BOTH_BASE_URL", "http://both.example.test")
    monkeypatch.setenv("THINGSBOARD_BOTH_API_KEY", "tb_secret")
    monkeypatch.setenv("THINGSBOARD_BOTH_USERNAME", "admin")
    monkeypatch.setenv("THINGSBOARD_BOTH_PASSWORD", "secret")

    captured = {}

    class RecordingClient:
        def __init__(
            self, base_url, username=None, password=None, *, api_key=None, discovery_ttl_seconds=3600
        ):
            captured["username"] = username
            captured["password"] = password
            captured["api_key"] = api_key

    monkeypatch.setattr(sources_module, "ThingsBoardClient", RecordingClient)

    sources_module._get_thingsboard_client("THINGSBOARD_BOTH")

    assert captured == {"username": None, "password": None, "api_key": "tb_secret"}


def test_get_thingsboard_client_uses_custom_credentials_env_prefix(monkeypatch):
    monkeypatch.setenv("THINGSBOARD_SVALBARD_BASE_URL", "http://svalbard.example.test")
    monkeypatch.setenv("THINGSBOARD_SVALBARD_USERNAME", "svalbard-admin")
    monkeypatch.setenv("THINGSBOARD_SVALBARD_PASSWORD", "svalbard-secret")

    captured = {}

    class RecordingClient:
        def __init__(self, base_url, username, password, *, discovery_ttl_seconds=3600):
            captured["base_url"] = base_url
            captured["username"] = username
            captured["password"] = password

    monkeypatch.setattr(sources_module, "ThingsBoardClient", RecordingClient)

    source = SourceEntry(
        id="s", type="thingsboard", config_provider="thingsboard",
        config_location="", data_location="", credentials_env_prefix="THINGSBOARD_SVALBARD",
    )
    provider = get_data_provider(source, base_dir=REPO_ROOT)

    assert captured == {
        "base_url": "http://svalbard.example.test",
        "username": "svalbard-admin",
        "password": "svalbard-secret",
    }
    assert isinstance(provider._client, RecordingClient)


def test_thingsboard_clients_are_cached_per_credentials_env_prefix(monkeypatch):
    monkeypatch.setenv("THINGSBOARD_A_BASE_URL", "http://a.example.test")
    monkeypatch.setenv("THINGSBOARD_A_USERNAME", "a")
    monkeypatch.setenv("THINGSBOARD_A_PASSWORD", "a-secret")
    monkeypatch.setenv("THINGSBOARD_B_BASE_URL", "http://b.example.test")
    monkeypatch.setenv("THINGSBOARD_B_USERNAME", "b")
    monkeypatch.setenv("THINGSBOARD_B_PASSWORD", "b-secret")

    client_a1 = sources_module._get_thingsboard_client("THINGSBOARD_A")
    client_a2 = sources_module._get_thingsboard_client("THINGSBOARD_A")
    client_b = sources_module._get_thingsboard_client("THINGSBOARD_B")

    assert client_a1 is client_a2
    assert client_a1 is not client_b


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
