from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from open_csi_publisher.core.config_schema import DatasetConfig
from open_csi_publisher.core.deployment import apply_deployment_metadata

TIME = pd.date_range("2020-01-01", periods=6, freq="365D")  # ~yearly steps, easy to reason about

BASE_FIXED = {
    "id": "station_a",
    "source_type": "loggernet",
    "access": "public",
    "source_config": {"file_pattern": "station_a/Table.dat"},
    "variables": [{"raw_name": "AirT_C", "standard_name": "air_temperature"}],
    "platform_type": "fixed",
    "deployments": [],
    "metadata": {"title": "Station A"},
    "output": {"file_naming": "{station}.nc"},
}

BASE_MOBILE = {
    "id": "boat_a",
    "source_type": "loggernet",
    "access": "public",
    "source_config": {"file_pattern": "boat_a/Table.dat"},
    "variables": [
        {"raw_name": "latitude", "standard_name": "latitude"},
        {"raw_name": "longitude", "standard_name": "longitude"},
    ],
    "platform_type": "mobile",
    "deployments": [],
    "metadata": {"title": "Boat A"},
    "output": {"file_naming": "{station}.nc"},
}


def _config(base: dict, deployments: list[dict]) -> DatasetConfig:
    doc = copy.deepcopy(base)
    doc["deployments"] = deployments
    return DatasetConfig.model_validate(doc)


def _ds() -> xr.Dataset:
    return xr.Dataset({"air_temperature": ("time", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])}, coords={"time": TIME})


def test_fixed_single_deployment_covers_all_timestamps():
    config = _config(
        BASE_FIXED,
        [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6, "elevation": 10}],
    )
    result = apply_deployment_metadata(_ds(), config)

    assert (result["latitude"].values == 78.0).all()
    assert (result["longitude"].values == 13.6).all()
    assert (result["elevation"].values == 10).all()


def test_fixed_two_deployments_switch_at_boundary():
    boundary = TIME[3]
    config = _config(
        BASE_FIXED,
        [
            {"start": "2020-01-01T00:00:00Z", "end": boundary.isoformat(), "lat": 78.0, "lon": 13.6},
            {"start": boundary.isoformat(), "end": None, "lat": 78.5, "lon": 14.0},
        ],
    )
    result = apply_deployment_metadata(_ds(), config)

    lat = result["latitude"].values
    assert list(lat[:3]) == [78.0, 78.0, 78.0]
    assert list(lat[3:]) == [78.5, 78.5, 78.5]


def test_fixed_timestamps_before_first_deployment_are_nan():
    config = _config(
        BASE_FIXED,
        [{"start": TIME[2].isoformat(), "end": None, "lat": 78.0, "lon": 13.6}],
    )
    result = apply_deployment_metadata(_ds(), config)

    lat = result["latitude"].values
    assert np.isnan(lat[:2]).all()
    assert (lat[2:] == 78.0).all()


def test_fixed_elevation_optional_stays_nan_when_unset():
    config = _config(
        BASE_FIXED, [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6}]
    )
    result = apply_deployment_metadata(_ds(), config)
    assert np.isnan(result["elevation"].values).all()


def test_fixed_coordinate_attrs_are_cf_compliant():
    config = _config(
        BASE_FIXED, [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6}]
    )
    result = apply_deployment_metadata(_ds(), config)
    assert result["latitude"].attrs["standard_name"] == "latitude"
    assert result["latitude"].attrs["units"] == "degrees_north"
    assert result["longitude"].attrs["standard_name"] == "longitude"
    assert result["longitude"].attrs["units"] == "degrees_east"


def _mobile_ds() -> xr.Dataset:
    return xr.Dataset(
        {
            "latitude": ("time", [78.1, 78.2, 78.3, 78.4, 78.5, 78.6]),
            "longitude": ("time", [15.1, 15.2, 15.3, 15.4, 15.5, 15.6]),
        },
        coords={"time": TIME},
    )


def test_mobile_does_not_touch_latitude_longitude_data():
    config = _config(
        BASE_MOBILE, [{"start": "2020-01-01T00:00:00Z", "end": None, "platform_name": "Example Boat"}]
    )
    raw = _mobile_ds()
    result = apply_deployment_metadata(raw, config)

    assert list(result["latitude"].values) == list(raw["latitude"].values)
    assert list(result["longitude"].values) == list(raw["longitude"].values)


def test_mobile_attaches_platform_coordinate():
    config = _config(
        BASE_MOBILE, [{"start": "2020-01-01T00:00:00Z", "end": None, "platform_name": "Example Boat"}]
    )
    result = apply_deployment_metadata(_mobile_ds(), config)
    assert (result["platform"].values == "Example Boat").all()


def test_mobile_platform_switches_at_deployment_boundary():
    boundary = TIME[3]
    config = _config(
        BASE_MOBILE,
        [
            {"start": "2020-01-01T00:00:00Z", "end": boundary.isoformat(), "platform_name": "Old Boat"},
            {"start": boundary.isoformat(), "end": None, "platform_name": "Example Boat"},
        ],
    )
    result = apply_deployment_metadata(_mobile_ds(), config)
    platform = result["platform"].values
    assert list(platform[:3]) == ["Old Boat"] * 3
    assert list(platform[3:]) == ["Example Boat"] * 3


def test_mobile_timestamps_before_first_deployment_platform_is_missing():
    config = _config(
        BASE_MOBILE, [{"start": TIME[2].isoformat(), "end": None, "platform_name": "Example Boat"}]
    )
    result = apply_deployment_metadata(_mobile_ds(), config)
    platform = result["platform"].values
    assert platform[0] is None or (isinstance(platform[0], float) and np.isnan(platform[0]))
    assert platform[2] == "Example Boat"
