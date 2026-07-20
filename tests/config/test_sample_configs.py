from __future__ import annotations

import pytest

from open_csi_publisher.core.config_schema import DatasetConfig
from open_csi_publisher.providers.config.folder import FolderConfigProvider

EXPECTED_SAMPLE_IDS = {
    "isfjord_radio_solar_park_measurements3": "fixed",
    "kapp_thordsen_10minute": "fixed",
    "hanna_resvoll_10min": "mobile",
}


def test_sample_config_dir_has_exactly_the_expected_datasets(sample_config_dir):
    provider = FolderConfigProvider(sample_config_dir)
    assert set(provider.list_dataset_ids()) == set(EXPECTED_SAMPLE_IDS)


@pytest.mark.parametrize("dataset_id,platform_type", EXPECTED_SAMPLE_IDS.items())
def test_sample_config_validates(sample_config_dir, dataset_id, platform_type):
    provider = FolderConfigProvider(sample_config_dir)
    config = DatasetConfig.model_validate(provider.load_config(dataset_id))
    assert config.id == dataset_id
    assert config.platform_type == platform_type
    assert config.access == "public"


def test_isfjord_config_has_department_metadata_for_filter_tests(sample_config_dir):
    provider = FolderConfigProvider(sample_config_dir)
    config = DatasetConfig.model_validate(
        provider.load_config("isfjord_radio_solar_park_measurements3")
    )
    assert config.metadata.model_extra["department"] == "Arctic Technology"


def test_hanna_resvoll_config_leaves_gps_location_unmapped(sample_config_dir):
    provider = FolderConfigProvider(sample_config_dir)
    config = DatasetConfig.model_validate(provider.load_config("hanna_resvoll_10min"))
    mapped_raw_names = {n for v in config.variables for n in v.all_raw_names()}
    assert "GPS_location" not in mapped_raw_names


def test_restricted_fixture_validates_and_is_restricted(fixture_config_dir):
    provider = FolderConfigProvider(fixture_config_dir)
    config = DatasetConfig.model_validate(provider.load_config("restricted_station"))
    assert config.access == "restricted"


def test_sources_yaml_references_real_paths(sample_config_dir):
    import yaml

    sources_doc = yaml.safe_load((sample_config_dir / "sources.yaml").read_text(encoding="utf-8"))
    assert sources_doc["sources"][0]["config_location"] == "sample_configs/"
    assert sources_doc["sources"][0]["data_location"] == "mount/loggernet-test-server/"
