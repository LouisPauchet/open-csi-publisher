from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from open_csi_publisher.core.config_schema import ExtraDimension, VariableMember, VariableSpec
from open_csi_publisher.core.variable_mapping import apply_variable_spec

TIME = pd.date_range("2026-01-01", periods=4, freq="10min")


def _ds(**data_vars: list[float]) -> xr.Dataset:
    return xr.Dataset({k: ("time", v) for k, v in data_vars.items()}, coords={"time": TIME})


def test_simple_variable_renamed_to_canonical_name_with_attrs():
    raw = _ds(AirT_C=[1.0, 2.0, 3.0, 4.0])
    spec = VariableSpec(raw_name="AirT_C", standard_name="air_temperature", units="degC")

    result = apply_variable_spec(raw, [spec])

    assert "air_temperature" in result.data_vars
    assert "AirT_C" not in result.data_vars
    assert list(result["air_temperature"].values) == [1.0, 2.0, 3.0, 4.0]
    assert result["air_temperature"].attrs["units"] == "degC"
    assert result["air_temperature"].attrs["standard_name"] == "air_temperature"


def test_variable_without_standard_name_keeps_raw_name_as_canonical():
    raw = _ds()
    raw["MetSENS_Status"] = ("time", np.array(["OK", "OK", "OK", "OK"], dtype=object))
    spec = VariableSpec(raw_name="MetSENS_Status", dtype="string")

    result = apply_variable_spec(raw, [spec])

    assert "MetSENS_Status" in result.data_vars


def test_old_names_fallback_when_raw_name_absent():
    raw = _ds(AirTemp_Avg=[5.0, 6.0, 7.0, 8.0])  # only the old column name is present
    spec = VariableSpec(
        raw_name="AirT_C", old_names=["AirTemp_Avg"], standard_name="air_temperature"
    )

    result = apply_variable_spec(raw, [spec])

    assert list(result["air_temperature"].values) == [5.0, 6.0, 7.0, 8.0]


def test_old_names_coalesced_across_a_rename_event():
    # simulates a reconciled fileset spanning a sensor rename: the old column is
    # populated for the first half, the new one for the second half, NaN elsewhere
    raw = _ds(
        AirTemp_Avg=[10.0, 11.0, np.nan, np.nan],
        AirT_C=[np.nan, np.nan, 13.0, 14.0],
    )
    spec = VariableSpec(
        raw_name="AirT_C", old_names=["AirTemp_Avg"], standard_name="air_temperature"
    )

    result = apply_variable_spec(raw, [spec])

    assert list(result["air_temperature"].values) == [10.0, 11.0, 13.0, 14.0]


def test_variable_missing_entirely_is_dropped_not_errored():
    raw = _ds(RH=[1.0, 2.0, 3.0, 4.0])
    spec = VariableSpec(raw_name="AirT_C", standard_name="air_temperature")

    result = apply_variable_spec(raw, [spec])

    assert "air_temperature" not in result.data_vars
    assert "AirT_C" not in result.data_vars


def test_extra_dimension_stacks_members_into_new_dimension():
    raw = _ds(
        AirTC_2m_Avg=[1.0, 2.0, 3.0, 4.0],
        AirTC_10m_Avg=[5.0, 6.0, 7.0, 8.0],
        AirTC_30m_Avg=[9.0, 10.0, 11.0, 12.0],
    )
    spec = VariableSpec(
        extra_dimension=ExtraDimension(name="height", units="m"),
        members=[
            VariableMember(raw_name="AirTC_2m_Avg", dimension_value=2),
            VariableMember(raw_name="AirTC_10m_Avg", dimension_value=10),
            VariableMember(raw_name="AirTC_30m_Avg", dimension_value=30),
        ],
        standard_name="air_temperature",
        units="degC",
    )

    result = apply_variable_spec(raw, [spec])

    var = result["air_temperature"]
    assert "height" in var.dims
    assert list(result["height"].values) == [2, 10, 30]
    assert var.sel(height=2).values.tolist() == [1.0, 2.0, 3.0, 4.0]
    assert var.sel(height=30).values.tolist() == [9.0, 10.0, 11.0, 12.0]


def test_extra_dimension_with_string_values_uses_object_dtype_not_fixed_width():
    # A plain python list of strings assigned as coordinate values gets
    # numpy's auto-inferred fixed-width "<U*" dtype by default. That dtype
    # breaks OPeNDAP serving: opendap-protocol's generic array encoder dumps
    # a fixed-width numpy string array's raw bytes straight onto the wire
    # with no per-element DAP2 length prefix, producing a DATADDS response
    # DAP clients reject as malformed ("NetCDF: Malformed or inaccessible
    # DAP2 DATADDS or DAP4 DAP response"). object dtype (genuine per-element
    # Python str) avoids that broken path — see variable_mapping.py.
    raw = _ds(
        wind_speed_raw_Avg=[1.0, 2.0, 3.0, 4.0],
        wind_speed_raw_Max=[5.0, 6.0, 7.0, 8.0],
        wind_speed_raw_Std=[0.1, 0.2, 0.3, 0.4],
    )
    spec = VariableSpec(
        extra_dimension=ExtraDimension(name="statistics", units="1"),
        members=[
            VariableMember(raw_name="wind_speed_raw_Avg", dimension_value="average"),
            VariableMember(raw_name="wind_speed_raw_Max", dimension_value="maximum"),
            VariableMember(raw_name="wind_speed_raw_Std", dimension_value="standard_deviation"),
        ],
        standard_name="wind_speed",
        units="m/s",
    )

    result = apply_variable_spec(raw, [spec])

    assert result["statistics"].values.dtype == np.dtype(object)
    assert list(result["statistics"].values) == ["average", "maximum", "standard_deviation"]
    assert result["wind_speed"].sel(statistics="maximum").values.tolist() == [5.0, 6.0, 7.0, 8.0]


def test_extra_dimension_missing_member_column_is_nan_not_dropped():
    # e.g. the 30m sensor didn't exist yet for this time window/file
    raw = _ds(
        AirTC_2m_Avg=[1.0, 2.0, 3.0, 4.0],
        AirTC_10m_Avg=[5.0, 6.0, 7.0, 8.0],
    )
    spec = VariableSpec(
        extra_dimension=ExtraDimension(name="height", units="m"),
        members=[
            VariableMember(raw_name="AirTC_2m_Avg", dimension_value=2),
            VariableMember(raw_name="AirTC_10m_Avg", dimension_value=10),
            VariableMember(raw_name="AirTC_30m_Avg", dimension_value=30),
        ],
        standard_name="air_temperature",
        units="degC",
    )

    result = apply_variable_spec(raw, [spec])

    var = result["air_temperature"]
    assert list(result["height"].values) == [2, 10, 30]
    assert bool(np.isnan(var.sel(height=30).values).all())
    assert var.sel(height=2).values.tolist() == [1.0, 2.0, 3.0, 4.0]


def test_extra_dimension_entirely_absent_is_dropped_not_errored():
    raw = _ds(RH=[1.0, 2.0, 3.0, 4.0])
    spec = VariableSpec(
        extra_dimension=ExtraDimension(name="height", units="m"),
        members=[VariableMember(raw_name="AirTC_2m_Avg", dimension_value=2)],
        standard_name="air_temperature",
    )

    result = apply_variable_spec(raw, [spec])

    assert "air_temperature" not in result.data_vars
