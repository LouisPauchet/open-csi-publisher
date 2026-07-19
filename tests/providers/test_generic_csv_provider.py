from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import pytest

from open_csi_publisher.core.config_schema import GenericCsvSourceConfig
from open_csi_publisher.providers.data.generic_csv.provider import GenericCsvDataProvider

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "generic_csv" / "data"
SOURCE_CONFIG = GenericCsvSourceConfig(file_path="station_x.csv")


@pytest.fixture
def data_root(tmp_path):
    shutil.copy(FIXTURE_DIR / "station_x.csv", tmp_path / "station_x.csv")
    return tmp_path


def test_get_file_index_initial_discovery(data_root):
    provider = GenericCsvDataProvider(data_root)
    records = provider.get_file_index(SOURCE_CONFIG)

    assert len(records) == 1
    record = records[0]
    assert record.file_role == "live"
    assert record.status == "active"
    assert record.time_start == datetime(2026, 1, 1, 0, 0, 0)
    assert record.time_end == datetime(2026, 1, 1, 0, 40, 0)
    assert "temp" in record.variables
    assert "humidity" in record.variables


def test_get_file_index_unchanged_mtime_flips_active_to_closed(data_root):
    provider = GenericCsvDataProvider(data_root)
    first = provider.get_file_index(SOURCE_CONFIG)
    second = provider.get_file_index(SOURCE_CONFIG, previous=first)

    assert second[0].status == "closed"
    assert second[0].size == first[0].size  # the mtime token, unchanged


def test_get_file_index_closed_file_reused_without_reparsing(data_root):
    provider = GenericCsvDataProvider(data_root)
    first = provider.get_file_index(SOURCE_CONFIG)
    closed = provider.get_file_index(SOURCE_CONFIG, previous=first)
    assert closed[0].status == "closed"

    # a further refresh with unchanged mtime must return the identical cached
    # record rather than re-reading the file
    third = provider.get_file_index(SOURCE_CONFIG, previous=closed)
    assert third[0] == closed[0]


def test_get_file_index_reparses_if_mtime_actually_changes(data_root):
    provider = GenericCsvDataProvider(data_root)
    first = provider.get_file_index(SOURCE_CONFIG)
    closed = provider.get_file_index(SOURCE_CONFIG, previous=first)

    path = data_root / "station_x.csv"
    with path.open("a", encoding="utf-8") as f:
        f.write("2026-01-01 00:50:00,3.5,55\n")
    # ensure the mtime actually advances even on coarse-grained filesystems
    new_time = time.time() + 5
    os.utime(path, (new_time, new_time))

    refreshed = provider.get_file_index(SOURCE_CONFIG, previous=closed)
    assert refreshed[0].status == "active"
    assert refreshed[0].time_end == datetime(2026, 1, 1, 0, 50, 0)
    assert refreshed[0].size != closed[0].size


def test_read_range_returns_dataset_with_expected_columns(data_root):
    provider = GenericCsvDataProvider(data_root)
    records = provider.get_file_index(SOURCE_CONFIG)
    ds = provider.read_range(SOURCE_CONFIG, files=records, start=None, end=None)

    assert "temp" in ds.data_vars
    assert "humidity" in ds.data_vars
    assert ds.sizes["time"] == 5


def test_read_range_time_window_slices(data_root):
    provider = GenericCsvDataProvider(data_root)
    records = provider.get_file_index(SOURCE_CONFIG)
    ds = provider.read_range(
        SOURCE_CONFIG,
        files=records,
        start=datetime(2026, 1, 1, 0, 10, 0),
        end=datetime(2026, 1, 1, 0, 30, 0),
    )
    assert ds.sizes["time"] == 3


def test_read_range_variables_restricts_columns(data_root):
    provider = GenericCsvDataProvider(data_root)
    records = provider.get_file_index(SOURCE_CONFIG)
    ds = provider.read_range(SOURCE_CONFIG, files=records, start=None, end=None, variables=["temp"])
    assert "temp" in ds.data_vars
    assert "humidity" not in ds.data_vars
