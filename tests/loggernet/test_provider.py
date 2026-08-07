from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from unittest.mock import patch

import numpy as np
import pytest

from open_csi_publisher.core.config_schema import LoggerNetSourceConfig
from open_csi_publisher.providers.data.loggernet import provider as provider_module
from open_csi_publisher.providers.data.loggernet.fileset import AmbiguousFileSetError
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


# --- get_file_index logging summary ----------------------------------------------


def test_get_file_index_logs_a_summary_of_matched_parsed_and_reused_files(tmp_path, caplog):
    (tmp_path / "Station_Table.dat").write_text(
        '"TOA5","Station","CR1000","12345","CR1000.Std.01","Program.CR1","1234","Table"\n'
        '"TIMESTAMP","RECORD","AirT_C"\n'
        '"TS","RN","Deg C"\n'
        '"","Smp","Avg"\n'
        '"2026-01-01 00:00:00",0,1.0\n',
        encoding="utf-8",
    )
    provider = LoggerNetDataProvider(tmp_path)
    config = LoggerNetSourceConfig(file_pattern="Station_Table.dat")

    caplog.clear()
    first = provider.get_file_index(config)
    assert "1 files matched" in caplog.text
    assert "1 newly parsed" in caplog.text

    caplog.clear()
    provider.get_file_index(config, previous=first)
    assert "0 newly parsed" in caplog.text
    assert "1 reused from previous index" in caplog.text


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


# --- get_file_index: no live file yet vs. genuinely ambiguous --------------------

_MINIMAL_TOA5 = (
    '"TOA5","Station","CR1000","12345","CR1000.Std.01","Program.CR1","1234","Table"\n'
    '"TIMESTAMP","RECORD","AirT_C"\n'
    '"TS","RN","Deg C"\n'
    '"","Smp","Avg"\n'
    '"2026-01-01 00:00:00",0,1.0\n'
)


def test_get_file_index_no_live_file_yet_returns_empty_list(tmp_path):
    # station configured, but the live file hasn't synced to the mount yet —
    # only the historical archive exists so far
    (tmp_path / "Station_Table_Historical.dat").write_text(_MINIMAL_TOA5, encoding="utf-8")
    provider = LoggerNetDataProvider(tmp_path)
    config = LoggerNetSourceConfig(file_pattern="Station_Table.dat")

    assert provider.get_file_index(config) == []


def test_get_file_index_no_live_file_yet_logs_a_warning(tmp_path, caplog):
    (tmp_path / "Station_Table_Historical.dat").write_text(_MINIMAL_TOA5, encoding="utf-8")
    provider = LoggerNetDataProvider(tmp_path)
    config = LoggerNetSourceConfig(file_pattern="Station_Table.dat")

    provider.get_file_index(config)
    assert "no live file" in caplog.text.lower()


def test_get_file_index_multiple_live_candidates_still_raises(tmp_path):
    # a genuine ambiguous-config problem (>1 live file) must stay loud, not
    # silently degrade like the zero-live-file "no data yet" case above
    for name in ("Station_TableA.dat", "Station_TableB.dat"):
        (tmp_path / name).write_text(_MINIMAL_TOA5, encoding="utf-8")
    provider = LoggerNetDataProvider(tmp_path)
    config = LoggerNetSourceConfig(file_pattern="Station_Table*.dat")

    with pytest.raises(AmbiguousFileSetError):
        provider.get_file_index(config)


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


# --- read_range parsed-file cache (state/cache.py) --------------------------------


class FakeCache:
    """A ParseCache/NullParseCache stand-in that records what was stored, so
    tests can assert both cache-hit behavior and (for the cache_enabled=False
    opt-out) that nothing was ever written at all."""

    enabled = True

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.set_calls: list[tuple[str, int]] = []

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: bytes, ttl: int) -> None:
        self.set_calls.append((key, ttl))
        self.store[key] = value


_TOA5_HEADER = (
    '"TOA5","Station","CR1000","12345","CR1000.Std.01","Program.CR1","1234","Table"\n'
    '"TIMESTAMP","RECORD","AirT_C"\n'
    '"TS","RN","Deg C"\n'
    '"","Smp","Avg"\n'
)


def _write_toa5(path, rows: list[tuple[str, int, float]]) -> None:
    body = "".join(f'"{ts}",{rec},{val}\n' for ts, rec, val in rows)
    path.write_text(_TOA5_HEADER + body, encoding="utf-8")


def test_read_range_caches_parsed_archived_file_and_never_reparses_it(tmp_path):
    _write_toa5(tmp_path / "Station_Table.dat", [("2026-01-01 00:10:00", 1, 2.0)])
    _write_toa5(tmp_path / "Station_Table_Historical.dat", [("2026-01-01 00:00:00", 0, 1.0)])
    config = LoggerNetSourceConfig(file_pattern="Station_Table.dat")
    provider = LoggerNetDataProvider(tmp_path, cache=FakeCache())
    records = provider.get_file_index(config)

    with patch.object(
        provider_module, "parse_toa5_file", wraps=provider_module.parse_toa5_file
    ) as spy:
        provider.read_range(config, files=records, start=None, end=None)
        provider.read_range(config, files=records, start=None, end=None)

        archived_calls = [c for c in spy.call_args_list if str(c.args[0]).endswith("_Historical.dat")]
        assert len(archived_calls) == 1


def test_read_range_caches_parsed_live_file_when_size_unchanged(tmp_path):
    _write_toa5(tmp_path / "Station_Table.dat", [("2026-01-01 00:10:00", 1, 2.0)])
    config = LoggerNetSourceConfig(file_pattern="Station_Table.dat")
    provider = LoggerNetDataProvider(tmp_path, cache=FakeCache())
    records = provider.get_file_index(config)

    with patch.object(
        provider_module, "parse_toa5_file", wraps=provider_module.parse_toa5_file
    ) as spy:
        provider.read_range(config, files=records, start=None, end=None)
        provider.read_range(config, files=records, start=None, end=None)
        assert spy.call_count == 1


def test_read_range_reparses_live_file_once_it_grows(tmp_path):
    live_path = tmp_path / "Station_Table.dat"
    _write_toa5(live_path, [("2026-01-01 00:10:00", 1, 2.0)])
    config = LoggerNetSourceConfig(file_pattern="Station_Table.dat")
    provider = LoggerNetDataProvider(tmp_path, cache=FakeCache())
    first_records = provider.get_file_index(config)

    provider.read_range(config, files=first_records, start=None, end=None)

    _write_toa5(
        live_path, [("2026-01-01 00:10:00", 1, 2.0), ("2026-01-01 00:20:00", 2, 3.0)]
    )
    second_records = provider.get_file_index(config, previous=first_records)

    with patch.object(
        provider_module, "parse_toa5_file", wraps=provider_module.parse_toa5_file
    ) as spy:
        result = provider.read_range(config, files=second_records, start=None, end=None)
        assert spy.call_count == 1
        assert result.sizes["time"] == 2


def test_read_range_without_a_cache_reparses_every_call(tmp_path):
    _write_toa5(tmp_path / "Station_Table.dat", [("2026-01-01 00:10:00", 1, 2.0)])
    _write_toa5(tmp_path / "Station_Table_Historical.dat", [("2026-01-01 00:00:00", 0, 1.0)])
    config = LoggerNetSourceConfig(file_pattern="Station_Table.dat")
    provider = LoggerNetDataProvider(tmp_path)  # no cache passed: today's behavior, unchanged
    records = provider.get_file_index(config)

    with patch.object(
        provider_module, "parse_toa5_file", wraps=provider_module.parse_toa5_file
    ) as spy:
        provider.read_range(config, files=records, start=None, end=None)
        provider.read_range(config, files=records, start=None, end=None)
        assert spy.call_count == 4  # 2 files x 2 calls, no caching at all


def test_read_range_without_a_real_cache_still_pushes_usecols_down(tmp_path):
    # cache_enabled defaults to True at the config level, but with no real cache
    # backing it (NullParseCache), the always-full-parse-then-subset tradeoff
    # isn't worth it — this must still take the cheaper partial-column read,
    # exactly like before caching existed at all.
    _write_toa5(tmp_path / "Station_Table.dat", [("2026-01-01 00:10:00", 1, 2.0)])
    config = LoggerNetSourceConfig(file_pattern="Station_Table.dat")
    provider = LoggerNetDataProvider(tmp_path)  # no cache passed -> NullParseCache
    records = provider.get_file_index(config)

    with patch.object(
        provider_module, "parse_toa5_file", wraps=provider_module.parse_toa5_file
    ) as spy:
        provider.read_range(config, files=records, start=None, end=None, variables=["AirT_C"])
        assert spy.call_args.kwargs.get("usecols") == ["AirT_C"]


def test_read_range_empty_files_returns_empty_dataset(tmp_path):
    provider = LoggerNetDataProvider(tmp_path)
    config = LoggerNetSourceConfig(file_pattern="Station_Table.dat")
    result = provider.read_range(config, files=[], start=None, end=None)
    assert result.sizes.get("time", 0) == 0


def test_read_range_cache_enabled_false_bypasses_caching_entirely(tmp_path):
    _write_toa5(tmp_path / "Station_Table.dat", [("2026-01-01 00:10:00", 1, 2.0)])
    _write_toa5(tmp_path / "Station_Table_Historical.dat", [("2026-01-01 00:00:00", 0, 1.0)])
    config = LoggerNetSourceConfig(file_pattern="Station_Table.dat", cache_enabled=False)
    fake_cache = FakeCache()
    provider = LoggerNetDataProvider(tmp_path, cache=fake_cache)
    records = provider.get_file_index(config)

    with patch.object(
        provider_module, "parse_toa5_file", wraps=provider_module.parse_toa5_file
    ) as spy:
        provider.read_range(config, files=records, start=None, end=None)
        provider.read_range(config, files=records, start=None, end=None)
        assert spy.call_count == 4  # 2 files x 2 calls: opt-out reparses every time

    assert fake_cache.store == {}  # never written to, not just never read from
