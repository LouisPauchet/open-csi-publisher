from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
import xarray as xr

from open_csi_publisher.core.builder import build_dataset_summary
from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.providers.base import DataProvider
from open_csi_publisher.providers.config.folder import DatasetConfigNotFoundError, FolderConfigProvider
from open_csi_publisher.providers.data.generic_csv.provider import GenericCsvDataProvider

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "generic_csv"


class _NoReadRangeProvider(DataProvider):
    """Wraps a real provider's get_file_index() but fails the test if
    read_range() is ever called — proves the fixed-station summary path
    never touches file bodies at all."""

    def __init__(self, delegate: DataProvider):
        self._delegate = delegate

    def get_file_index(self, source_config, previous=()):
        return self._delegate.get_file_index(source_config, previous=previous)

    def read_range(self, *args, **kwargs):
        raise AssertionError("read_range should never be called for a fixed-station summary")


@pytest.fixture
def fixed_config_provider():
    return FolderConfigProvider(FIXTURE_ROOT / "configs")


@pytest.fixture
def fixed_data_provider():
    return _NoReadRangeProvider(GenericCsvDataProvider(FIXTURE_ROOT / "data"))


def test_summary_fixed_station_geospatial_bounds_from_deployment_config_only(
    db_session, fixed_config_provider, fixed_data_provider
):
    metadata, coverage = build_dataset_summary(
        "generic_csv_demo",
        session=db_session,
        config_provider=fixed_config_provider,
        data_provider=fixed_data_provider,
    )
    assert metadata["geospatial_lat_min"] == 60.0
    assert metadata["geospatial_lat_max"] == 60.0
    assert metadata["geospatial_lon_min"] == 10.0
    assert metadata["geospatial_lon_max"] == 10.0


def test_summary_time_coverage_matches_known_bounds(db_session, fixed_config_provider, fixed_data_provider):
    metadata, coverage = build_dataset_summary(
        "generic_csv_demo",
        session=db_session,
        config_provider=fixed_config_provider,
        data_provider=fixed_data_provider,
    )
    assert coverage == (datetime(2026, 1, 1, 0, 0, 0), datetime(2026, 1, 1, 0, 40, 0))
    assert metadata["time_coverage_start"] == "2026-01-01T00:00:00Z"
    assert metadata["time_coverage_end"] == "2026-01-01T00:40:00Z"


def test_summary_includes_provenance_and_global_attrs(db_session, fixed_config_provider, fixed_data_provider):
    metadata, _ = build_dataset_summary(
        "generic_csv_demo",
        session=db_session,
        config_provider=fixed_config_provider,
        data_provider=fixed_data_provider,
    )
    assert metadata["unis_id"] == "generic_csv_demo"
    assert "id" not in metadata
    assert metadata["processing_software_version"]
    assert metadata["config_hash"]
    assert "history" in metadata


def test_summary_unknown_id_raises(db_session, fixed_config_provider, fixed_data_provider):
    with pytest.raises(DatasetConfigNotFoundError):
        build_dataset_summary(
            "does_not_exist",
            session=db_session,
            config_provider=fixed_config_provider,
            data_provider=fixed_data_provider,
        )


class _RecordingDataProvider(DataProvider):
    """Returns a scripted file index and a scripted read_range() result,
    recording exactly which files each read_range() call was given."""

    def __init__(self, file_index: list[FileRecord], dataset: xr.Dataset):
        self._file_index = file_index
        self._dataset = dataset
        self.read_range_calls: list[list[FileRecord]] = []

    def get_file_index(self, source_config, previous=()):
        return self._file_index

    def read_range(self, source_config, files, start, end, variables=None):
        self.read_range_calls.append(list(files))
        return self._dataset


_ARCHIVED = FileRecord(
    file_name="archived.dat",
    file_role="archived",
    size=100,
    time_start=datetime(2020, 1, 1),
    time_end=datetime(2020, 1, 2),
    variables=["latitude", "longitude"],
    status="closed",
)
_LIVE = FileRecord(
    file_name="live.dat",
    file_role="live",
    size=50,
    time_start=datetime(2026, 1, 1),
    time_end=datetime(2026, 1, 2),
    variables=["latitude", "longitude"],
    status="active",
)


def test_summary_mobile_station_reads_only_the_live_file(db_session, sample_config_dir):
    config_provider = FolderConfigProvider(sample_config_dir)
    fake_dataset = xr.Dataset(
        {"latitude": ("time", [78.1, 78.3]), "longitude": ("time", [15.1, 15.4])},
        coords={"time": pd.DatetimeIndex([datetime(2026, 1, 1), datetime(2026, 1, 1, 1)])},
    )
    provider = _RecordingDataProvider([_ARCHIVED, _LIVE], fake_dataset)

    metadata, coverage = build_dataset_summary(
        "hanna_resvoll_10min", session=db_session, config_provider=config_provider, data_provider=provider
    )

    assert len(provider.read_range_calls) == 1
    assert provider.read_range_calls[0] == [_LIVE]  # the archived file is never touched
    assert metadata["geospatial_lat_min"] == pytest.approx(78.1)
    assert metadata["geospatial_lat_max"] == pytest.approx(78.3)
    assert metadata["geospatial_lon_min"] == pytest.approx(15.1)
    assert metadata["geospatial_lon_max"] == pytest.approx(15.4)
    # time coverage still spans the FULL index (both files), unlike the
    # geospatial bounds which are deliberately live-file-only
    assert coverage == (datetime(2020, 1, 1), datetime(2026, 1, 2))


def test_summary_mobile_station_with_no_live_file_omits_geospatial_attrs(db_session, sample_config_dir):
    config_provider = FolderConfigProvider(sample_config_dir)
    provider = _RecordingDataProvider([_ARCHIVED], xr.Dataset())

    metadata, coverage = build_dataset_summary(
        "hanna_resvoll_10min", session=db_session, config_provider=config_provider, data_provider=provider
    )

    assert provider.read_range_calls == []
    assert "geospatial_lat_min" not in metadata
    assert coverage == (datetime(2020, 1, 1), datetime(2020, 1, 2))


def test_summary_empty_file_index_has_no_time_coverage(db_session, fixed_config_provider):
    provider = _RecordingDataProvider([], xr.Dataset())
    metadata, coverage = build_dataset_summary(
        "generic_csv_demo", session=db_session, config_provider=fixed_config_provider, data_provider=provider
    )
    assert coverage is None
    assert "time_coverage_start" not in metadata
