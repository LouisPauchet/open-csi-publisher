from __future__ import annotations

from open_csi_publisher.core.config_schema import DatasetConfig
from open_csi_publisher.core.search_index import build_search_document
from open_csi_publisher.providers.config.folder import FolderConfigProvider


def _load(sample_config_dir, dataset_id: str) -> DatasetConfig:
    provider = FolderConfigProvider(sample_config_dir)
    return DatasetConfig.model_validate(provider.load_config(dataset_id))


def test_metadata_kv_includes_open_ended_extra_keys(sample_config_dir):
    config = _load(sample_config_dir, "isfjord_radio_solar_park_measurements3")
    doc = build_search_document(config)

    assert doc.metadata_kv["department"] == "Arctic Technology"
    assert doc.metadata_kv["title"] == "UNIS AT Example Solar Park AWS"
    # unset optional metadata fields (license, naming_authority) are not present
    assert "license" not in doc.metadata_kv


def test_metadata_kv_omits_unset_optional_fields(sample_config_dir):
    config = _load(sample_config_dir, "hanna_resvoll_10min")
    doc = build_search_document(config)
    assert "license" not in doc.metadata_kv
    assert "naming_authority" not in doc.metadata_kv


def test_text_blob_is_lowercased_and_searchable(sample_config_dir):
    config = _load(sample_config_dir, "isfjord_radio_solar_park_measurements3")
    doc = build_search_document(config)

    assert "arctic technology" in doc.text_blob
    assert "isfjord" in doc.text_blob
    assert doc.dataset_id in doc.text_blob


def test_standard_names_collected_skips_variables_without_one(sample_config_dir):
    config = _load(sample_config_dir, "isfjord_radio_solar_park_measurements3")
    doc = build_search_document(config)

    assert "air_temperature" in doc.standard_names
    assert "relative_humidity" in doc.standard_names
    # MetSENS_Status has no standard_name and must not leak in as one
    assert "MetSENS_Status" not in doc.standard_names
    assert None not in doc.standard_names


def test_extra_dimension_group_standard_name_included_once(sample_config_dir):
    config = _load(sample_config_dir, "isfjord_radio_solar_park_measurements3")
    doc = build_search_document(config)
    assert "surface_downwelling_shortwave_flux_in_air" in doc.standard_names


def test_access_and_platform_type_carried_through(sample_config_dir):
    fixed = build_search_document(_load(sample_config_dir, "kapp_thordsen_10minute"))
    mobile = build_search_document(_load(sample_config_dir, "hanna_resvoll_10min"))

    assert fixed.access == "public"
    assert fixed.platform_type == "fixed"
    assert mobile.platform_type == "mobile"


def test_dataset_id_matches_config_id(sample_config_dir):
    config = _load(sample_config_dir, "kapp_thordsen_10minute")
    doc = build_search_document(config)
    assert doc.dataset_id == "kapp_thordsen_10minute"
