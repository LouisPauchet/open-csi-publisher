from __future__ import annotations

import math
import time
from datetime import datetime

import pandas as pd
import pytest

from open_csi_publisher.providers.data.loggernet.toa5 import (
    parse_toa5_file,
    parse_toa5_header,
)

from ..conftest import requires_mount

FIVELFLYENE_MIN = (
    "UNIS_AGF_Fivelflyene_Adventdalen_AWS"
    "/UNIS_AGF_Fivelflyene_Adventdalen_AWS_Min.dat"
)
ISFJORD_LIVE = (
    "UNIS_AT_Isfjord_Radio_Solar_Park_AWS"
    "/UNIS_AT_Isfjord_Radio_Solar_Park_AWS_Measurements_3.dat"
)
KAPP_THORDSEN_HISTORICAL = (
    "UNIS_AGF_Kapp_Thordsen_AWS"
    "/UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute_Historical.dat"
)
FIVELFLYENE_MIN_HISTORICAL = (
    "UNIS_AGF_Fivelflyene_Adventdalen_AWS"
    "/UNIS_AGF_Fivelflyene_Adventdalen_AWS_Min_Historical.dat"
)


@requires_mount
def test_parse_toa5_header_matches_real_file(mount_root):
    header = parse_toa5_header(mount_root / FIVELFLYENE_MIN)
    assert header.station_name == "UNIS_AGF_Fivelflyene_Adventdalen_AWS"
    assert header.logger_model == "CR1000"
    assert header.serial_no == "10333"
    assert header.program_name == "CPU:1852_20200707_str.CR1"
    assert header.table_name == "Min"
    assert header.column_names[:3] == ["TIMESTAMP", "RECORD", "BattV_Min"]
    assert header.units[2] == "Volts"
    assert header.agg_types[2] == "Min"


@requires_mount
def test_parse_toa5_file_full_small_real_file(mount_root):
    parsed = parse_toa5_file(mount_root / ISFJORD_LIVE)
    assert parsed.n_rows == 6581
    assert parsed.time_start == datetime(2026, 7, 18, 19, 52, 40)
    assert parsed.time_end == datetime(2026, 7, 19, 14, 9, 20)

    ds = parsed.dataset
    assert "time" in ds.dims
    assert ds.sizes["time"] == 6581
    # numeric column
    assert pd.api.types.is_float_dtype(ds["WS_ms"].dtype)
    # quoted non-numeric status column stays string/object, not coerced to numeric
    assert ds["MetSENS_Status"].dtype == object
    assert set(ds["MetSENS_Status"].values[:5].tolist()) <= {"OK"}
    # RECORD is present as an ordinary variable, never consulted for ordering
    assert "RECORD" in ds.data_vars


@requires_mount
def test_uppercase_nan_sentinel_becomes_real_nan(mount_root):
    parsed = parse_toa5_file(mount_root / KAPP_THORDSEN_HISTORICAL)
    ds = parsed.dataset
    first_row = ds.isel(time=0)
    assert math.isnan(float(first_row["wind_speed_Avg"].values))
    assert math.isnan(float(first_row["air_pressure_Avg"].values))
    # a real (non-"NAN") string value in the same row is left untouched
    assert str(first_row["MetSENS_Status"].values) == "Unknown Fault"


@requires_mount
def test_storage_corruption_bytes_do_not_abort_the_parse(mount_root):
    # UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute_Historical.dat has 7 rows where a
    # quoted field's content was overwritten with raw 0xFF bytes (likely unwritten
    # flash after a power loss), while the surrounding quotes/delimiters stayed
    # intact. The parse must not raise; the affected rows are still present, just
    # with a garbled value in that one field instead of the real one.
    parsed = parse_toa5_file(mount_root / KAPP_THORDSEN_HISTORICAL)
    assert parsed.n_rows > 0
    status_values = parsed.dataset["MetSENS_Status"].values
    assert any("�" in str(v) for v in status_values)


@requires_mount
def test_usecols_always_includes_timestamp_column(mount_root):
    parsed = parse_toa5_file(mount_root / ISFJORD_LIVE, usecols=["WS_ms"])
    assert "WS_ms" in parsed.dataset.data_vars
    assert "MetSENS_Status" not in parsed.dataset.data_vars
    assert parsed.n_rows == 6581
    assert parsed.time_start == datetime(2026, 7, 18, 19, 52, 40)


@requires_mount
def test_header_attrs_and_per_variable_unit_attrs_attached(mount_root):
    parsed = parse_toa5_file(mount_root / ISFJORD_LIVE)
    assert parsed.dataset.attrs["station_name"] == "UNIS_AT_Isfjord_Radio_Solar_Park_AWS"
    assert parsed.dataset.attrs["table_name"] == "Measurements_3"
    assert parsed.dataset["WS_ms"].attrs["loggernet_units"] == "meters/second"


@requires_mount
def test_empty_file_time_bounds_are_none(mount_root, tmp_path):
    header_lines = (mount_root / ISFJORD_LIVE).read_text(encoding="utf-8").splitlines()[:4]
    empty_file = tmp_path / "empty.dat"
    # write_bytes, not write_text: write_text re-translates \n to os.linesep on
    # Windows, which would double the CRLFs already in the joined string.
    empty_file.write_bytes(("\r\n".join(header_lines) + "\r\n").encode("utf-8"))

    parsed = parse_toa5_file(empty_file)
    assert parsed.n_rows == 0
    assert parsed.time_start is None
    assert parsed.time_end is None


@requires_mount
@pytest.mark.slow
def test_large_historical_file_parses_and_reports_timing(mount_root):
    path = mount_root / FIVELFLYENE_MIN_HISTORICAL
    started = time.monotonic()
    parsed = parse_toa5_file(path)
    elapsed = time.monotonic() - started
    assert parsed.n_rows > 0
    print(
        f"\n[slow] full-parse of {path.name} "
        f"({path.stat().st_size / 1_000_000:.0f} MB, {parsed.n_rows} rows) took {elapsed:.1f}s"
    )
