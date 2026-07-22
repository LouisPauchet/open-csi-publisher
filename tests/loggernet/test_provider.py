from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from unittest.mock import patch

import numpy as np

from open_csi_publisher.core.config_schema import LoggerNetSourceConfig
from open_csi_publisher.providers.data.loggernet import provider as provider_module
from open_csi_publisher.providers.data.loggernet.provider import LoggerNetDataProvider

from ..conftest import requires_mount

KAPP_THORDSEN_PATTERN = "UNIS_AGF_Kapp_Thordsen_AWS/UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute.dat"
ISFJORD_PATTERN = (
    "UNIS_AT_Isfjord_Radio_Solar_Park_AWS/UNIS_AT_Isfjord_Radio_Solar_Park_AWS_Measurements_3.dat"
)
HANNA_RESVOLL_PATTERN = "UNIS_AGF_Boat_Hanna_Resvoll/UNIS_AGF_Boat_Hanna_Resvoll_AWS_Table_10min.dat"


def _kapp_thordsen_config(**overrides) -> LoggerNetSourceConfig:
    return LoggerNetSourceConfig(file_pattern=KAPP_THORDSEN_PATTERN, **overrides)


# --- _historical_pattern / _backup_pattern --------------------------------------


def test_historical_pattern_dot_dat_regression():
    assert (
        provider_module._historical_pattern("Station_Table.dat", "_Historical")
        == "Station_Table_Historical.dat"
    )


def test_historical_pattern_generalizes_beyond_dot_dat():
    assert (
        provider_module._historical_pattern("Station_Table.csv", "_Historical")
        == "Station_Table_Historical.csv"
    )


def test_historical_pattern_handles_pattern_without_an_extension():
    assert (
        provider_module._historical_pattern("Station_Table", "_Historical")
        == "Station_Table_Historical"
    )


def test_backup_pattern_is_extension_agnostic():
    assert provider_module._backup_pattern("Station_Table.csv") == "Station_Table.csv.backup*"


# --- matched_files skips non-TOA5 files ------------------------------------------


def test_matched_files_skips_files_without_a_toa5_header(tmp_path):
    valid = tmp_path / "Station_Table.csv"
    valid.write_text(
        '"TOA5","Station","CR1000","12345","CR1000.Std.01","Program.CR1","1234","Table"\n'
        '"TIMESTAMP","RECORD","Var1"\n'
        '"TS","RN","Volts"\n'
        '"","Smp","Avg"\n'
        '"2026-01-01 00:00:00",0,1.0\n',
        encoding="utf-8",
    )
    not_toa5 = tmp_path / "Station_Table_notes.csv"
    not_toa5.write_text("just,some,other,csv,content\n1,2,3,4,5\n", encoding="utf-8")

    provider = LoggerNetDataProvider(tmp_path)
    config = LoggerNetSourceConfig(file_pattern="Station_Table*.csv")
    matched = provider.matched_files(config)

    assert matched == [valid]


def test_matched_files_logs_a_warning_via_loguru_for_each_skipped_file(tmp_path, caplog):
    (tmp_path / "Station_Table.csv").write_text(
        '"TOA5","Station","CR1000","12345","CR1000.Std.01","Program.CR1","1234","Table"\n'
        '"TIMESTAMP","RECORD","Var1"\n'
        '"TS","RN","Volts"\n'
        '"","Smp","Avg"\n'
        '"2026-01-01 00:00:00",0,1.0\n',
        encoding="utf-8",
    )
    not_toa5 = tmp_path / "Station_Table_notes.csv"
    not_toa5.write_text("just,some,other,csv,content\n1,2,3,4,5\n", encoding="utf-8")

    provider = LoggerNetDataProvider(tmp_path)
    config = LoggerNetSourceConfig(file_pattern="Station_Table*.csv")
    provider.matched_files(config)

    assert "skipping" in caplog.text
    assert str(not_toa5) in caplog.text


def test_get_file_index_ignores_non_toa5_files_matching_the_glob(tmp_path):
    valid = tmp_path / "Station_Table.csv"
    valid.write_text(
        '"TOA5","Station","CR1000","12345","CR1000.Std.01","Program.CR1","1234","Table"\n'
        '"TIMESTAMP","RECORD","Var1"\n'
        '"TS","RN","Volts"\n'
        '"","Smp","Avg"\n'
        '"2026-01-01 00:00:00",0,1.0\n',
        encoding="utf-8",
    )
    (tmp_path / "Station_Table_notes.csv").write_text(
        "just,some,other,csv,content\n1,2,3,4,5\n", encoding="utf-8"
    )

    provider = LoggerNetDataProvider(tmp_path)
    config = LoggerNetSourceConfig(file_pattern="Station_Table*.csv")
    records = provider.get_file_index(config)

    assert [r.file_name for r in records] == [valid.name]


@requires_mount
def test_get_file_index_initial_discovery(mount_root):
    provider = LoggerNetDataProvider(mount_root)
    records = provider.get_file_index(_kapp_thordsen_config())

    by_role = {r.file_role: r for r in records}
    assert by_role["archived"].status == "closed"
    assert by_role["archived"].file_name.endswith("_Historical.dat")
    assert by_role["archived"].time_end == datetime(2026, 3, 10, 12, 50, 0)

    assert by_role["live"].status == "active"
    assert by_role["live"].time_start == datetime(2026, 7, 17, 11, 30, 0)
    assert "surface_temperature_Avg" in by_role["live"].variables


@requires_mount
def test_get_file_index_matches_dot_backup_convention(mount_root):
    provider = LoggerNetDataProvider(mount_root)
    records = provider.get_file_index(LoggerNetSourceConfig(file_pattern=ISFJORD_PATTERN))
    roles = {r.file_role for r in records}
    assert roles == {"live", "archived"}
    archived = next(r for r in records if r.file_role == "archived")
    assert archived.file_name.endswith(".dat.backup")
    assert archived.status == "closed"


@requires_mount
def test_get_file_index_does_not_confuse_prefix_overlapping_table_names(mount_root):
    # Fivelflyene has Min, Min10, and Min60 tables (each with its own live+historical
    # pair) — a naive "*_Min*" glob would also match Min10/Min60 files. file_pattern
    # must resolve to exactly the Min table's own two files.
    provider = LoggerNetDataProvider(mount_root)
    config = LoggerNetSourceConfig(
        file_pattern="UNIS_AGF_Fivelflyene_Adventdalen_AWS/UNIS_AGF_Fivelflyene_Adventdalen_AWS_Min.dat"
    )
    records = provider.get_file_index(config)
    names = {r.file_name for r in records}
    assert names == {
        "UNIS_AGF_Fivelflyene_Adventdalen_AWS/UNIS_AGF_Fivelflyene_Adventdalen_AWS_Min.dat",
        "UNIS_AGF_Fivelflyene_Adventdalen_AWS/UNIS_AGF_Fivelflyene_Adventdalen_AWS_Min_Historical.dat",
    }


@requires_mount
def test_get_file_index_never_reparses_closed_archived_file(mount_root):
    provider = LoggerNetDataProvider(mount_root)
    with patch.object(
        provider_module, "parse_toa5_file", wraps=provider_module.parse_toa5_file
    ) as spy:
        first = provider.get_file_index(_kapp_thordsen_config())
        assert spy.call_count == 2  # archived + live, both new

        spy.reset_mock()
        provider.get_file_index(_kapp_thordsen_config(), previous=first)
        # archived file is closed and already known: must not be reparsed
        parsed_paths = [str(call.args[0]) for call in spy.call_args_list]
        assert not any(p.endswith("_Historical.dat") for p in parsed_paths)


@requires_mount
def test_get_file_index_unchanged_live_file_flips_active_to_closed(mount_root):
    provider = LoggerNetDataProvider(mount_root)
    first = provider.get_file_index(_kapp_thordsen_config())
    live_first = next(r for r in first if r.file_role == "live")
    assert live_first.status == "active"

    second = provider.get_file_index(_kapp_thordsen_config(), previous=first)
    live_second = next(r for r in second if r.file_role == "live")
    assert live_second.status == "closed"
    assert live_second.size == live_first.size


@requires_mount
def test_get_file_index_closed_live_file_reparsed_if_size_actually_differs(mount_root):
    # simulates the belt-and-suspenders case: a live file recorded as "closed" with a
    # stale size gets re-stat'd, found to differ, and is treated as reopened
    provider = LoggerNetDataProvider(mount_root)
    first = provider.get_file_index(_kapp_thordsen_config())
    live_first = next(r for r in first if r.file_role == "live")
    stale_closed = [
        replace(r, status="closed", size=r.size - 1) if r.file_role == "live" else r
        for r in first
    ]

    second = provider.get_file_index(_kapp_thordsen_config(), previous=stale_closed)
    live_second = next(r for r in second if r.file_role == "live")
    assert live_second.status == "active"
    assert live_second.size == live_first.size


@requires_mount
def test_get_file_index_closed_live_file_unchanged_stays_closed_without_reparse(mount_root):
    provider = LoggerNetDataProvider(mount_root)
    first = provider.get_file_index(_kapp_thordsen_config())
    already_closed = [
        replace(r, status="closed") if r.file_role == "live" else r for r in first
    ]

    with patch.object(
        provider_module, "parse_toa5_file", wraps=provider_module.parse_toa5_file
    ) as spy:
        second = provider.get_file_index(_kapp_thordsen_config(), previous=already_closed)
        assert spy.call_count == 0

    live_second = next(r for r in second if r.file_role == "live")
    assert live_second.status == "closed"


@requires_mount
def test_read_range_full_window_matches_reconciled_dataset(mount_root):
    provider = LoggerNetDataProvider(mount_root)
    config = _kapp_thordsen_config()
    records = provider.get_file_index(config)

    combined = provider.read_range(config, files=records, start=None, end=None)
    assert "surface_temperature_Avg" in combined.data_vars
    time_values = combined["time"].values
    assert np.all(np.diff(time_values) > np.timedelta64(0, "s"))


@requires_mount
def test_read_range_time_window_slices_result(mount_root):
    provider = LoggerNetDataProvider(mount_root)
    config = _kapp_thordsen_config()
    records = provider.get_file_index(config)

    sliced = provider.read_range(
        config,
        files=records,
        start=datetime(2026, 7, 17, 11, 30, 0),
        end=datetime(2026, 7, 18, 0, 0, 0),
    )
    time_values = sliced["time"].values
    assert time_values.min() >= np.datetime64(datetime(2026, 7, 17, 11, 30, 0))
    assert time_values.max() <= np.datetime64(datetime(2026, 7, 18, 0, 0, 0))


@requires_mount
def test_read_range_archived_only_never_touches_live_file(mount_root):
    provider = LoggerNetDataProvider(mount_root)
    config = _kapp_thordsen_config()
    records = provider.get_file_index(config)
    archived_only = [r for r in records if r.file_role == "archived"]

    result = provider.read_range(config, files=archived_only, start=None, end=None)
    assert result["time"].values.max() <= np.datetime64(datetime(2026, 3, 10, 12, 50, 0))


@requires_mount
def test_read_range_variables_restricts_columns(mount_root):
    provider = LoggerNetDataProvider(mount_root)
    config = _kapp_thordsen_config()
    records = provider.get_file_index(config)

    result = provider.read_range(
        config, files=records, start=None, end=None, variables=["wind_speed_Avg"]
    )
    assert "wind_speed_Avg" in result.data_vars
    assert "relative_humidity_Avg" not in result.data_vars
