from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from open_csi_publisher.core.builder import build_dataset
from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.providers.data.generic_csv.provider import GenericCsvDataProvider
from open_csi_publisher.providers.data.loggernet.provider import LoggerNetDataProvider

from ..conftest import requires_mount

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "generic_csv"


@pytest.fixture
def config_provider():
    return FolderConfigProvider(FIXTURE_ROOT / "configs")


@pytest.fixture
def data_provider():
    return GenericCsvDataProvider(FIXTURE_ROOT / "data")


def test_build_dataset_attaches_acdd_coverage_attrs_for_a_fixed_station(
    db_session, config_provider, data_provider
):
    ds = build_dataset(
        "generic_csv_demo", session=db_session, config_provider=config_provider, data_provider=data_provider
    )

    # a fixed station's position is constant, so min == max
    assert ds.attrs["geospatial_lat_min"] == 60.0
    assert ds.attrs["geospatial_lat_max"] == 60.0
    assert ds.attrs["geospatial_lon_min"] == 10.0
    assert ds.attrs["geospatial_lon_max"] == 10.0
    assert ds.attrs["time_coverage_start"] == "2026-01-01T00:00:00Z"
    assert ds.attrs["time_coverage_end"] == "2026-01-01T00:40:00Z"


def test_coverage_attrs_are_native_python_floats_not_numpy(db_session, config_provider, data_provider):
    # attrs end up in JSON responses (REST /data, CSV headers) and NetCDF
    # global attrs — a numpy.float64 works for the latter but not always
    # cleanly for the former, so these must be plain Python floats.
    ds = build_dataset(
        "generic_csv_demo", session=db_session, config_provider=config_provider, data_provider=data_provider
    )
    assert type(ds.attrs["geospatial_lat_min"]) is float
    assert type(ds.attrs["geospatial_lon_max"]) is float


@pytest.fixture
def loggernet_config_provider(sample_config_dir):
    return FolderConfigProvider(sample_config_dir)


@pytest.fixture
def loggernet_data_provider(mount_root):
    return LoggerNetDataProvider(mount_root)


@requires_mount
def test_mobile_dataset_lat_lon_coverage_reflects_real_track_extent(
    db_session, loggernet_config_provider, loggernet_data_provider
):
    ds = build_dataset(
        "hanna_resvoll_10min",
        session=db_session,
        config_provider=loggernet_config_provider,
        data_provider=loggernet_data_provider,
    )
    assert ds.attrs["geospatial_lat_min"] == pytest.approx(float(ds["latitude"].min()))
    assert ds.attrs["geospatial_lat_max"] == pytest.approx(float(ds["latitude"].max()))
    assert ds.attrs["geospatial_lon_min"] == pytest.approx(float(ds["longitude"].min()))
    assert ds.attrs["geospatial_lon_max"] == pytest.approx(float(ds["longitude"].max()))


@requires_mount
def test_coverage_attrs_reflect_a_narrowed_time_window_not_the_full_dataset(
    db_session, loggernet_config_provider, loggernet_data_provider
):
    ds = build_dataset(
        "kapp_thordsen_10minute",
        start=datetime(2026, 7, 17, 11, 30, 0),
        end=datetime(2026, 7, 18, 0, 0, 0),
        session=db_session,
        config_provider=loggernet_config_provider,
        data_provider=loggernet_data_provider,
    )
    assert ds.attrs["time_coverage_start"].startswith("2026-07-17")
    assert ds.attrs["time_coverage_end"].startswith("2026-07-17") or ds.attrs[
        "time_coverage_end"
    ].startswith("2026-07-18")


@requires_mount
def test_geospatial_attrs_omitted_when_position_not_in_requested_variables(
    db_session, loggernet_config_provider, loggernet_data_provider
):
    # narrowing a mobile dataset to variables that exclude latitude/longitude
    # drops those coordinates entirely (variable_mapping narrows before
    # deployment metadata is applied) — coverage attrs must be omitted, not
    # raise, matching how the rest of the pipeline treats missing data.
    ds = build_dataset(
        "hanna_resvoll_10min",
        variables=["wind_speed"],
        session=db_session,
        config_provider=loggernet_config_provider,
        data_provider=loggernet_data_provider,
    )
    assert "latitude" not in ds.variables
    assert "geospatial_lat_min" not in ds.attrs
    assert "geospatial_lon_min" not in ds.attrs
    # time coverage is always present regardless of variable narrowing
    assert "time_coverage_start" in ds.attrs
