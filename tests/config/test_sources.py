from __future__ import annotations

import pytest

from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.providers.data.loggernet.provider import LoggerNetDataProvider
from open_csi_publisher.sources import (
    SourceEntry,
    get_config_provider,
    get_data_provider,
    list_all_datasets,
    load_sources,
)

from ..conftest import REPO_ROOT, requires_mount


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
