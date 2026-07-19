from __future__ import annotations

from pathlib import Path

import pytest

from open_csi_publisher.cli.matching import (
    detect_extra_dimension_groups,
    detect_gps_columns,
    detect_old_name_matches,
    load_known_variables,
    suggest_standard_name,
)
from open_csi_publisher.core.config_schema import VariableSpec
from open_csi_publisher.providers.data.loggernet.toa5 import parse_toa5_header

from ..conftest import requires_mount

KAPP_THORDSEN = (
    "UNIS_AGF_Kapp_Thordsen_AWS/UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute.dat"
)
HANNA_RESVOLL = "UNIS_AGF_Boat_Hanna_Resvoll/UNIS_AGF_Boat_Hanna_Resvoll_AWS_Table_10min.dat"


@pytest.fixture
def known_variables():
    return load_known_variables()


def test_known_variables_loads_real_yaml(known_variables):
    assert known_variables["wind_speed_Avg"]["standard_name"] == "wind_speed"
    assert known_variables["latitude"]["standard_name"] == "latitude"


@requires_mount
def test_suggest_standard_name_against_real_kapp_thordsen_columns(mount_root, known_variables):
    header = parse_toa5_header(mount_root / KAPP_THORDSEN)
    suggestions = {
        col: suggest_standard_name(col, known_variables) for col in header.column_names
    }
    assert suggestions["wind_speed_Avg"]["standard_name"] == "wind_speed"
    assert suggestions["air_pressure_Avg"]["standard_name"] == "air_pressure"
    assert suggestions["relative_humidity_Avg"]["standard_name"] == "relative_humidity"
    assert suggestions["dewpoint_temperature_Avg"]["standard_name"] == "dew_point_temperature"
    # a raw status/id column has no sensible suggestion
    assert suggestions["MetSENS_Status"] is None
    assert suggestions["RECORD"] is None


def test_suggest_standard_name_exact_match():
    known = {"AirT_C": {"standard_name": "air_temperature", "units": "degC"}}
    assert suggest_standard_name("AirT_C", known)["standard_name"] == "air_temperature"


def test_suggest_standard_name_fuzzy_match_close_variant():
    known = {"wind_speed_Avg": {"standard_name": "wind_speed", "units": "m/s"}}
    result = suggest_standard_name("wind_speed_avg", known)  # case variant
    assert result is not None
    assert result["standard_name"] == "wind_speed"


def test_suggest_standard_name_no_match_returns_none():
    known = {"AirT_C": {"standard_name": "air_temperature", "units": "degC"}}
    assert suggest_standard_name("completely_unrelated_column_xyz", known) is None


# --- GPS column detection -------------------------------------------------------


@requires_mount
def test_detect_gps_columns_against_real_hanna_resvoll(mount_root):
    header = parse_toa5_header(mount_root / HANNA_RESVOLL)
    detected = detect_gps_columns(header.column_names)
    assert detected["latitude"] == "latitude"
    assert detected["longitude"] == "longitude"


def test_detect_gps_columns_case_insensitive_variants():
    detected = detect_gps_columns(["Lat", "Lon", "AirTemp"])
    assert detected == {"Lat": "latitude", "Lon": "longitude"}


def test_detect_gps_columns_empty_when_none_present():
    assert detect_gps_columns(["AirT_C", "RH", "BP_mbar"]) == {}


# --- extra_dimension grouping detection (synthetic: no real station has this) --


def test_detect_extra_dimension_groups_finds_leveled_columns():
    columns = ["AirTC_2m_Avg", "AirTC_10m_Avg", "AirTC_30m_Avg", "RH", "BP_mbar"]
    groups = detect_extra_dimension_groups(columns)
    assert len(groups) == 1
    group = groups[0]
    assert group["dimension_units"] == "m"
    values = [m["dimension_value"] for m in group["members"]]
    assert values == [2, 10, 30]
    raw_names = [m["raw_name"] for m in group["members"]]
    assert raw_names == ["AirTC_2m_Avg", "AirTC_10m_Avg", "AirTC_30m_Avg"]


def test_detect_extra_dimension_groups_ignores_single_member_patterns():
    # a lone leveled column isn't a "group" worth combining
    columns = ["AirTC_2m_Avg", "RH"]
    assert detect_extra_dimension_groups(columns) == []


def test_detect_extra_dimension_groups_none_when_no_pattern_present():
    assert detect_extra_dimension_groups(["AirT_C", "RH", "BP_mbar"]) == []


# --- old_names re-run detection (synthetic: simulates a rename event) ----------


def test_detect_old_name_matches_classifies_columns():
    existing = [
        VariableSpec(raw_name="AirT_C", standard_name="air_temperature"),
        VariableSpec(raw_name="RH", old_names=["OldRH"], standard_name="relative_humidity"),
    ]
    new_columns = ["AirT_C", "OldRH", "AirT_Celsius", "BrandNewColumn"]

    result = detect_old_name_matches(new_columns, existing)

    assert result["AirT_C"] == "already_mapped"
    assert result["OldRH"] == "already_mapped"  # matches an existing old_names entry
    assert result["AirT_Celsius"] == "likely_rename"  # fuzzy-matches AirT_C
    assert result["BrandNewColumn"] == "new"
