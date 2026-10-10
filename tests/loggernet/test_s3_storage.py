"""LoggerNet provider reading straight from S3 must match the local-folder behaviour
and must never write to the bucket."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import fsspec
import pytest

from open_csi_publisher.core.config_schema import LoggerNetSourceConfig
from open_csi_publisher.providers.data.loggernet.provider import LoggerNetDataProvider
from open_csi_publisher.providers.data.loggernet.toa5 import (
    parse_toa5_file,
    parse_toa5_header,
    parse_toa5_start_time,
)
from open_csi_publisher.storage import LocalStorage, S3Storage, StorageFile

HEADER = (
    '"TOA5","Station","CR1000","12345","CR1000.Std.01","Program.CR1","1234","Table"\n'
    '"TIMESTAMP","RECORD","AirT_C"\n'
    '"TS","RN","Deg C"\n'
    '"","Smp","Avg"\n'
)
LIVE = HEADER + '"2026-01-02 00:00:00",2,2.0\n"2026-01-02 00:10:00",3,3.0\n'
HISTORICAL = HEADER + '"2026-01-01 00:00:00",0,0.5\n"2026-01-01 00:10:00",1,1.0\n'
NOTES = "just,some,notes\n1,2,3\n"
FILES = {
    "st/Station_Table.dat": LIVE,
    "st/Station_Table_Historical.dat": HISTORICAL,
    "st/Station_Table_notes.dat": NOTES,
}
CONFIG = LoggerNetSourceConfig(file_pattern="st/Station_Table.dat")


@pytest.fixture
def local_provider(tmp_path: Path) -> LoggerNetDataProvider:
    for rel, content in FILES.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
    return LoggerNetDataProvider(tmp_path)


@pytest.fixture
def s3_fs():
    fs = fsspec.filesystem("memory")
    fs.store.clear()
    fs.pseudo_dirs[:] = [""]
    for rel, content in FILES.items():
        fs.pipe_file(f"/bkt/{rel}", content.encode())
    return fs


@pytest.fixture
def s3_provider(s3_fs) -> LoggerNetDataProvider:
    return LoggerNetDataProvider(S3Storage(fs=s3_fs, bucket="bkt"))


def _snapshot(fs):
    return {k: fs.cat_file(k) for k in fs.find("/bkt")}


def test_toa5_functions_accept_storage_files(s3_fs):
    f = StorageFile(S3Storage(fs=s3_fs, bucket="bkt"), "st/Station_Table.dat")
    assert parse_toa5_header(f).column_names == ["TIMESTAMP", "RECORD", "AirT_C"]
    assert parse_toa5_start_time(f) == datetime(2026, 1, 2, 0, 0)
    parsed = parse_toa5_file(f)
    assert parsed.n_rows == 2
    assert "s3://bkt/st/Station_Table.dat" in parsed.dataset.attrs["source_file"]


def test_matched_files_over_s3_skips_non_toa5(s3_provider):
    cfg = LoggerNetSourceConfig(file_pattern="st/Station_Table*.dat")
    assert s3_provider.matched_files(cfg) == [
        "st/Station_Table.dat",
        "st/Station_Table_Historical.dat",
    ]


def test_file_index_over_s3_matches_local(local_provider, s3_provider):
    local = local_provider.get_file_index(CONFIG)
    remote = s3_provider.get_file_index(CONFIG)
    assert [r.file_name for r in remote] == ["st/Station_Table_Historical.dat", "st/Station_Table.dat"]
    assert remote == local


def test_read_range_over_s3_matches_local(local_provider, s3_provider):
    records = s3_provider.get_file_index(CONFIG)
    remote = s3_provider.read_range(CONFIG, records, None, None)
    local = local_provider.read_range(CONFIG, records, None, None)
    assert remote["AirT_C"].values.tolist() == [0.5, 1.0, 2.0, 3.0]
    assert remote["AirT_C"].values.tolist() == local["AirT_C"].values.tolist()


def test_incremental_refresh_over_s3_reuses_closed_records(s3_provider):
    first = s3_provider.get_file_index(CONFIG)
    second = s3_provider.get_file_index(CONFIG, previous=first)
    assert [r.file_name for r in second] == [r.file_name for r in first]


def test_provider_never_writes_to_the_bucket(s3_provider, s3_fs):
    before = _snapshot(s3_fs)
    records = s3_provider.get_file_index(CONFIG)
    s3_provider.read_range(CONFIG, records, None, None)
    s3_provider.get_file_index(CONFIG, previous=records)
    assert _snapshot(s3_fs) == before


def test_local_storage_object_is_accepted(tmp_path, local_provider):
    p = LoggerNetDataProvider(LocalStorage(tmp_path))
    assert p.get_file_index(CONFIG) == local_provider.get_file_index(CONFIG)
