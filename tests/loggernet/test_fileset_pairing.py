from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from open_csi_publisher.providers.data.loggernet.fileset import (
    AmbiguousFileSetError,
    classify_files,
    reconcile_fileset,
)
from open_csi_publisher.providers.data.loggernet.toa5 import parse_toa5_file

from ..conftest import requires_mount

FIVELFLYENE = "UNIS_AGF_Fivelflyene_Adventdalen_AWS"
KAPP_THORDSEN = "UNIS_AGF_Kapp_Thordsen_AWS"
ISFJORD = "UNIS_AT_Isfjord_Radio_Solar_Park_AWS"
HANNA_RESVOLL = "UNIS_AGF_Boat_Hanna_Resvoll"


def _paths(mount_root: Path, station: str, *names: str) -> list[Path]:
    return [mount_root / station / name for name in names]


# --- classify_files -----------------------------------------------------------


@requires_mount
def test_classify_files_historical_suffix(mount_root):
    matched = _paths(
        mount_root,
        KAPP_THORDSEN,
        "UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute.dat",
        "UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute_Historical.dat",
    )
    classified = classify_files(matched)
    by_role = {c.role: c.path for c in classified}
    assert by_role["live"].name == "UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute.dat"
    assert by_role["archived"].name == "UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute_Historical.dat"


@requires_mount
def test_classify_files_dot_backup_convention(mount_root):
    matched = _paths(
        mount_root,
        ISFJORD,
        "UNIS_AT_Isfjord_Radio_Solar_Park_AWS_Measurements_3.dat",
        "UNIS_AT_Isfjord_Radio_Solar_Park_AWS_Measurements_3.dat.backup",
    )
    classified = classify_files(matched)
    roles = {c.path.name: c.role for c in classified}
    assert roles["UNIS_AT_Isfjord_Radio_Solar_Park_AWS_Measurements_3.dat"] == "live"
    assert roles["UNIS_AT_Isfjord_Radio_Solar_Park_AWS_Measurements_3.dat.backup"] == "archived"


def test_classify_files_numbered_backup_rotation_recognized(tmp_path):
    live = tmp_path / "Station_Table.dat"
    backup1 = tmp_path / "Station_Table.dat.backup1"
    for p in (live, backup1):
        p.write_text("x")
    classified = classify_files([live, backup1])
    roles = {c.path.name: c.role for c in classified}
    assert roles[backup1.name] == "archived"


def test_classify_files_no_live_candidate_raises(tmp_path):
    only_archived = tmp_path / "Station_Table_Historical.dat"
    only_archived.write_text("x")
    with pytest.raises(AmbiguousFileSetError):
        classify_files([only_archived])


def test_classify_files_multiple_live_candidates_raises(tmp_path):
    a = tmp_path / "Station_TableA.dat"
    b = tmp_path / "Station_TableB.dat"
    for p in (a, b):
        p.write_text("x")
    with pytest.raises(AmbiguousFileSetError):
        classify_files([a, b])


def test_classify_files_live_only_is_fine(tmp_path):
    live = tmp_path / "Station_Table.dat"
    live.write_text("x")
    classified = classify_files([live])
    assert [c.role for c in classified] == ["live"]


# --- reconcile_fileset ----------------------------------------------------------


@requires_mount
def test_reconcile_contiguous_fivelflyene_min10(mount_root):
    live = parse_toa5_file(
        mount_root / FIVELFLYENE / "UNIS_AGF_Fivelflyene_Adventdalen_AWS_Min10.dat"
    )
    archived = parse_toa5_file(
        mount_root / FIVELFLYENE / "UNIS_AGF_Fivelflyene_Adventdalen_AWS_Min10_Historical.dat"
    )
    combined = reconcile_fileset(archived=[archived], live=live)

    # the archived file alone has ~12k internally duplicated timestamps (a real
    # clock-reset/backfill artifact); reconciliation must dedup those too, so the
    # combined row count is strictly less than the naive sum, not equal to it
    assert combined.sizes["time"] < archived.n_rows + live.n_rows

    time_values = combined["time"].values
    assert np.all(np.diff(time_values) > np.timedelta64(0, "s"))  # strictly increasing

    # contiguous at the live/archived boundary: no synthesized/missing rows
    last_archived = np.datetime64(datetime(2026, 6, 29, 10, 0, 0))
    first_live = np.datetime64(datetime(2026, 6, 29, 10, 10, 0))
    idx = list(time_values).index(last_archived)
    assert time_values[idx + 1] == first_live


@requires_mount
def test_reconcile_gapped_and_drifted_kapp_thordsen(mount_root):
    live = parse_toa5_file(
        mount_root / KAPP_THORDSEN / "UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute.dat"
    )
    archived = parse_toa5_file(
        mount_root
        / KAPP_THORDSEN
        / "UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute_Historical.dat"
    )
    combined = reconcile_fileset(archived=[archived], live=live)

    # strictly increasing despite the RECORD reset in the live file
    time_values = combined["time"].values
    assert np.all(np.diff(time_values) > np.timedelta64(0, "s"))

    # the real gap is preserved as a gap, not interpolated/synthesized
    last_historical = np.datetime64(datetime(2026, 3, 10, 12, 50, 0))
    first_live = np.datetime64(datetime(2026, 7, 17, 11, 30, 0))
    idx = list(time_values).index(last_historical)
    assert time_values[idx + 1] == first_live

    # column drift: surface_temperature_Avg only exists in the live file
    surface_temp = combined["surface_temperature_Avg"]
    historical_slice = surface_temp.sel(time=slice(None, last_historical))
    live_slice = surface_temp.sel(time=slice(first_live, None))
    assert bool(np.isnan(historical_slice.values).all())
    assert bool(np.isfinite(live_slice.values).any())


@requires_mount
def test_reconcile_logs_program_name_mismatch(mount_root, caplog):
    live = parse_toa5_file(
        mount_root / KAPP_THORDSEN / "UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute.dat"
    )
    archived = parse_toa5_file(
        mount_root
        / KAPP_THORDSEN
        / "UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute_Historical.dat"
    )
    assert live.header.program_name != archived.header.program_name
    with caplog.at_level(logging.INFO):
        reconcile_fileset(archived=[archived], live=live)
    assert any("program_name" in r.message for r in caplog.records)


@requires_mount
def test_reconcile_live_only_dataset_is_passthrough(mount_root):
    live = parse_toa5_file(
        mount_root
        / HANNA_RESVOLL
        / "UNIS_AGF_Boat_Hanna_Resvoll_AWS_Table_10min.dat"
    )
    combined = reconcile_fileset(archived=[], live=live)
    assert combined.sizes["time"] == live.n_rows
    assert combined["time"].values[0] == np.datetime64(live.time_start)
    assert combined["time"].values[-1] == np.datetime64(live.time_end)


@requires_mount
def test_reconcile_archived_only_when_query_predates_live_file(mount_root):
    # a query covering only an old window can be answered from archived files
    # alone, with the live file never even opened
    archived = parse_toa5_file(
        mount_root / KAPP_THORDSEN / "UNIS_AGF_Kapp_Thordsen_AWS_Table_10minute_Historical.dat"
    )
    combined = reconcile_fileset(archived=[archived], live=None)
    assert combined.sizes["time"] <= archived.n_rows
    assert "surface_temperature_Avg" not in combined.data_vars


def test_reconcile_requires_at_least_one_file():
    with pytest.raises(ValueError):
        reconcile_fileset(archived=[], live=None)
