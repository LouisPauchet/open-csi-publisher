from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from open_csi_publisher.core.config_schema import DatasetConfig

FIXED_CONFIG = {
    "id": "isfjord_radio_solar_park_measurements3",
    "source_type": "loggernet",
    "access": "public",
    "source_config": {
        "file_pattern": "UNIS_AT_Isfjord_Radio_Solar_Park_AWS/UNIS_AT_Isfjord_Radio_Solar_Park_AWS_Measurements_3.dat*",
    },
    "variables": [
        {"raw_name": "AirT_C", "standard_name": "air_temperature", "units": "degC"},
        {"raw_name": "MetSENS_Status", "dtype": "string"},
    ],
    "platform_type": "fixed",
    "deployments": [
        {"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.06, "lon": 13.63, "elevation": 10},
    ],
    "metadata": {"title": "Isfjord Radio Solar Park AWS", "department": "Arctic Technology"},
    "output": {"file_naming": "{station}_{table}_{yyyy}-{mm}.nc"},
}

MOBILE_CONFIG = {
    "id": "hanna_resvoll_10min",
    "source_type": "loggernet",
    "access": "public",
    "source_config": {
        "file_pattern": "UNIS_AGF_Boat_Hanna_Resvoll/UNIS_AGF_Boat_Hanna_Resvoll_AWS_Table_10min.dat*",
    },
    "variables": [
        {"raw_name": "latitude", "standard_name": "latitude"},
        {"raw_name": "longitude", "standard_name": "longitude"},
        {"raw_name": "wind_speed_corrected_Avg", "standard_name": "wind_speed", "units": "m/s"},
    ],
    "platform_type": "mobile",
    "deployments": [
        {"start": "2026-05-18T00:00:00Z", "end": None, "platform_name": "R/V Hanna Resvoll"},
    ],
    "metadata": {"title": "Hanna Resvoll boat AWS"},
    "output": {"file_naming": "{station}_{table}_{yyyy}-{mm}.nc"},
}


def _mutate(base: dict, **kwargs) -> dict:
    doc = copy.deepcopy(base)
    for key, value in kwargs.items():
        doc[key] = value
    return doc


def test_valid_fixed_config_loads():
    config = DatasetConfig.model_validate(FIXED_CONFIG)
    assert config.platform_type == "fixed"
    assert config.deployments[0].lat == 78.06


def test_valid_mobile_config_loads():
    config = DatasetConfig.model_validate(MOBILE_CONFIG)
    assert config.platform_type == "mobile"
    assert config.deployments[0].platform_name == "R/V Hanna Resvoll"


def test_metadata_preserves_extra_open_ended_keys():
    config = DatasetConfig.model_validate(FIXED_CONFIG)
    assert config.metadata.model_extra["department"] == "Arctic Technology"


def test_canonical_name_prefers_standard_name():
    config = DatasetConfig.model_validate(FIXED_CONFIG)
    air_temp = next(v for v in config.variables if v.raw_name == "AirT_C")
    status = next(v for v in config.variables if v.raw_name == "MetSENS_Status")
    assert air_temp.canonical_name == "air_temperature"
    assert status.canonical_name == "MetSENS_Status"


def test_extra_dimension_variable_requires_standard_name_and_members():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["variables"].append(
        {
            "extra_dimension": {"name": "pyr_channel", "units": "nm"},
            "members": [
                {"raw_name": "pyr_3364", "dimension_value": 3364},
                {"raw_name": "pyr_1550", "dimension_value": 1550},
            ],
            "standard_name": "surface_downwelling_shortwave_flux_in_air",
        }
    )
    config = DatasetConfig.model_validate(doc)
    grouped = next(v for v in config.variables if v.extra_dimension is not None)
    assert grouped.canonical_name == "surface_downwelling_shortwave_flux_in_air"
    assert len(grouped.members) == 2


def test_extra_dimension_without_members_rejected():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["variables"].append(
        {
            "extra_dimension": {"name": "pyr_channel", "units": "nm"},
            "members": [],
            "standard_name": "x",
        }
    )
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_extra_dimension_without_standard_name_rejected():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["variables"].append(
        {
            "extra_dimension": {"name": "pyr_channel", "units": "nm"},
            "members": [{"raw_name": "pyr_3364", "dimension_value": 3364}],
        }
    )
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_variable_without_raw_name_or_extra_dimension_rejected():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["variables"].append({"standard_name": "orphan"})
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_variable_with_both_raw_name_and_extra_dimension_rejected():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["variables"].append(
        {
            "raw_name": "x",
            "extra_dimension": {"name": "height", "units": "m"},
            "members": [{"raw_name": "x_2m", "dimension_value": 2}],
            "standard_name": "y",
        }
    )
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_duplicate_raw_name_across_variables_rejected():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["variables"].append({"raw_name": "AirT_C", "standard_name": "dup"})
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_old_name_colliding_with_another_variables_raw_name_rejected():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["variables"][0]["old_names"] = ["MetSENS_Status"]
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_fixed_deployment_missing_lat_lon_rejected():
    doc = _mutate(FIXED_CONFIG, deployments=[{"start": "2020-01-01T00:00:00Z", "end": None}])
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_fixed_deployment_with_platform_name_rejected():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["deployments"][0]["platform_name"] = "should not be here"
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_mobile_deployment_missing_platform_name_rejected():
    doc = _mutate(MOBILE_CONFIG, deployments=[{"start": "2026-05-18T00:00:00Z", "end": None}])
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_mobile_deployment_with_lat_rejected():
    doc = copy.deepcopy(MOBILE_CONFIG)
    doc["deployments"][0]["lat"] = 78.0
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_mobile_without_latitude_longitude_variables_rejected():
    doc = copy.deepcopy(MOBILE_CONFIG)
    doc["variables"] = [{"raw_name": "wind_speed_corrected_Avg", "standard_name": "wind_speed"}]
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_deployments_must_be_sorted_and_non_overlapping():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["deployments"] = [
        {"start": "2022-01-01T00:00:00Z", "end": None, "lat": 78.06, "lon": 13.63},
        {"start": "2020-01-01T00:00:00Z", "end": "2022-06-01T00:00:00Z", "lat": 78.0, "lon": 13.6},
    ]
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_only_last_deployment_may_be_open_ended():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["deployments"] = [
        {"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6},
        {"start": "2022-01-01T00:00:00Z", "end": None, "lat": 78.06, "lon": 13.63},
    ]
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_overlapping_deployments_rejected():
    doc = copy.deepcopy(FIXED_CONFIG)
    doc["deployments"] = [
        {"start": "2020-01-01T00:00:00Z", "end": "2022-06-01T00:00:00Z", "lat": 78.0, "lon": 13.6},
        {"start": "2022-01-01T00:00:00Z", "end": None, "lat": 78.06, "lon": 13.63},
    ]
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)
