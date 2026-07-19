from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.state import repository
from open_csi_publisher.state.models import Base, FileIndexEntry


def test_create_all_creates_expected_tables(sqlite_engine):
    table_names = set(inspect(sqlite_engine).get_table_names())
    assert {"config_versions", "file_index", "publish_log"} <= table_names


def test_get_current_config_version_none_when_unrecorded(db_session):
    assert repository.get_current_config_version(db_session, "station_a") is None


def test_config_version_current_is_most_recently_recorded(db_session):
    repository.record_config_version(db_session, "station_a", "hash1", {"id": "station_a", "v": 1})
    repository.record_config_version(db_session, "station_a", "hash2", {"id": "station_a", "v": 2})

    current = repository.get_current_config_version(db_session, "station_a")
    assert current.hash == "hash2"
    assert current.content["v"] == 2


def test_config_version_isolated_per_dataset(db_session):
    repository.record_config_version(db_session, "station_a", "hash_a", {"id": "station_a"})
    repository.record_config_version(db_session, "station_b", "hash_b", {"id": "station_b"})

    assert repository.get_current_config_version(db_session, "station_a").hash == "hash_a"
    assert repository.get_current_config_version(db_session, "station_b").hash == "hash_b"


def test_file_index_upsert_inserts_new_entry(db_session):
    record = FileRecord(
        file_name="station_a/Table.dat",
        file_role="live",
        size=100,
        time_start=datetime(2026, 1, 1),
        time_end=datetime(2026, 1, 2),
        variables=["AirT_C"],
        status="active",
    )
    repository.upsert_file_index_entry(db_session, "station_a", record)

    entries = repository.list_file_index(db_session, "station_a")
    assert entries == [record]


def test_file_index_upsert_updates_existing_entry_in_place(db_session):
    record = FileRecord(
        file_name="station_a/Table.dat",
        file_role="live",
        size=100,
        time_start=datetime(2026, 1, 1),
        time_end=datetime(2026, 1, 2),
        variables=["AirT_C"],
        status="active",
    )
    repository.upsert_file_index_entry(db_session, "station_a", record)

    updated = FileRecord(
        file_name="station_a/Table.dat",
        file_role="live",
        size=250,
        time_start=datetime(2026, 1, 1),
        time_end=datetime(2026, 1, 3),
        variables=["AirT_C", "RH"],
        status="closed",
    )
    repository.upsert_file_index_entry(db_session, "station_a", updated)

    entries = repository.list_file_index(db_session, "station_a")
    assert entries == [updated]


def test_file_index_unique_constraint_on_dataset_and_file_name(db_session):
    db_session.add(
        FileIndexEntry(
            dataset_id="station_a",
            file_name="station_a/Table.dat",
            file_role="live",
            size=1,
            time_start=None,
            time_end=None,
            variables=[],
            status="active",
        )
    )
    db_session.flush()
    db_session.add(
        FileIndexEntry(
            dataset_id="station_a",
            file_name="station_a/Table.dat",
            file_role="live",
            size=2,
            time_start=None,
            time_end=None,
            variables=[],
            status="active",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_get_publish_log_entry_none_when_unrecorded(db_session):
    assert repository.get_publish_log_entry(db_session, "station_a", "2026-01") is None


def test_record_and_get_publish_log_entry(db_session):
    repository.record_publish_log_entry(
        db_session,
        dataset_id="station_a",
        period="2026-01",
        config_hash="hash1",
        software_version="0.1.0",
        cached_file_path="local/publish_cache/station_a/2026-01.nc",
    )
    entry = repository.get_publish_log_entry(db_session, "station_a", "2026-01")
    assert entry is not None
    assert entry.config_hash == "hash1"
    assert entry.cached_file_path == "local/publish_cache/station_a/2026-01.nc"


def test_publish_log_entry_isolated_per_dataset_and_period(db_session):
    repository.record_publish_log_entry(
        db_session, dataset_id="station_a", period="2026-01",
        config_hash="h1", software_version="0.1.0", cached_file_path="a.nc",
    )
    repository.record_publish_log_entry(
        db_session, dataset_id="station_a", period="2026-02",
        config_hash="h2", software_version="0.1.0", cached_file_path="b.nc",
    )
    repository.record_publish_log_entry(
        db_session, dataset_id="station_b", period="2026-01",
        config_hash="h3", software_version="0.1.0", cached_file_path="c.nc",
    )
    assert repository.get_publish_log_entry(db_session, "station_a", "2026-01").cached_file_path == "a.nc"
    assert repository.get_publish_log_entry(db_session, "station_a", "2026-02").cached_file_path == "b.nc"
    assert repository.get_publish_log_entry(db_session, "station_b", "2026-01").cached_file_path == "c.nc"
