from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from open_csi_publisher.core.builder import build_dataset
from open_csi_publisher.providers.config.folder import (
    DatasetConfigNotFoundError,
    FolderConfigProvider,
)
from open_csi_publisher.providers.data.loggernet.provider import LoggerNetDataProvider

from ..conftest import requires_mount


@pytest.fixture
def config_provider(sample_config_dir):
    return FolderConfigProvider(sample_config_dir)


@pytest.fixture
def data_provider(mount_root):
    return LoggerNetDataProvider(mount_root)


@requires_mount
def test_build_isfjord_fixed_dataset_end_to_end(db_session, config_provider, data_provider):
    ds = build_dataset(
        "isfjord_radio_solar_park_measurements3",
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )

    assert "air_temperature" in ds.data_vars
    assert "relative_humidity" in ds.data_vars
    assert "wind_speed" in ds.data_vars
    assert ds["MetSENS_Status"].dtype == object

    # unconfigured raw columns are dropped, not carried through
    assert "BattV" not in ds.data_vars
    assert "RECORD" not in ds.data_vars
    assert "CS241T_C" not in ds.data_vars

    # extra_dimension pyranometer grouping
    var = ds["surface_downwelling_shortwave_flux_in_air"]
    assert "sensor_channel" in var.dims
    assert list(ds["sensor_channel"].values) == [1, 2, 3, 4]

    # fixed platform: constant resolved position
    assert (ds["latitude"].values == 78.0).all()
    assert (ds["longitude"].values == 15.0).all()

    assert ds.attrs["title"] == "UNIS AT Example Solar Park AWS"
    assert ds.attrs["department"] == "Arctic Technology"


@requires_mount
def test_build_kapp_thordsen_gap_and_column_drift_end_to_end(
    db_session, config_provider, data_provider
):
    ds = build_dataset(
        "kapp_thordsen_10minute",
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )

    time_values = ds["time"].values
    assert np.all(np.diff(time_values) > np.timedelta64(0, "s"))

    last_historical = np.datetime64(datetime(2026, 3, 10, 12, 50, 0))
    first_live = np.datetime64(datetime(2026, 7, 17, 11, 30, 0))
    surface_temp = ds["surface_temperature"]
    assert bool(np.isnan(surface_temp.sel(time=slice(None, last_historical)).values).all())
    assert bool(np.isfinite(surface_temp.sel(time=slice(first_live, None)).values).any())

    assert (ds["latitude"].values == 78.5).all()


@requires_mount
def test_build_hanna_resvoll_mobile_dataset_end_to_end(db_session, config_provider, data_provider):
    ds = build_dataset(
        "hanna_resvoll_10min",
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )

    # position is real per-timestep data, never overwritten by deployment resolution
    assert float(ds["latitude"].isel(time=0).values) == pytest.approx(78.22824)
    assert float(ds["longitude"].isel(time=0).values) == pytest.approx(15.60777)

    assert (ds["platform"].values == "Example Boat").all()

    # raw vs. motion-corrected wind both present, distinctly
    assert "wind_speed" in ds.data_vars  # corrected -> canonical
    assert "wind_speed_raw_Avg" in ds.data_vars  # raw, kept as-is

    # deliberately unmapped composite column is dropped
    assert "GPS_location" not in ds.data_vars


@requires_mount
def test_build_dataset_time_window_narrows_result(db_session, config_provider, data_provider):
    ds = build_dataset(
        "kapp_thordsen_10minute",
        start=datetime(2026, 7, 17, 11, 30, 0),
        end=datetime(2026, 7, 18, 0, 0, 0),
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )
    time_values = ds["time"].values
    assert time_values.min() >= np.datetime64(datetime(2026, 7, 17, 11, 30, 0))
    assert time_values.max() <= np.datetime64(datetime(2026, 7, 18, 0, 0, 0))


@requires_mount
def test_build_dataset_accepts_timezone_aware_start_and_end(db_session, config_provider, data_provider):
    # A REST query param like "?start=2026-07-17T11:30:00.000Z" (exactly what
    # JS's Date.toISOString() produces, e.g. static/js/map.js's mobile-track
    # fetch) is parsed by FastAPI/pydantic into a timezone-aware datetime —
    # raw LoggerNet timestamps and the file index are naive, so without
    # normalization this raises "can't compare offset-naive and
    # offset-aware datetimes" instead of narrowing the result.
    ds = build_dataset(
        "kapp_thordsen_10minute",
        start=datetime(2026, 7, 17, 11, 30, 0, tzinfo=timezone.utc),
        end=datetime(2026, 7, 18, 0, 0, 0, tzinfo=timezone.utc),
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )
    time_values = ds["time"].values
    assert time_values.min() >= np.datetime64(datetime(2026, 7, 17, 11, 30, 0))
    assert time_values.max() <= np.datetime64(datetime(2026, 7, 18, 0, 0, 0))


@requires_mount
def test_build_dataset_variables_filter_restricts_output(db_session, config_provider, data_provider):
    ds = build_dataset(
        "isfjord_radio_solar_park_measurements3",
        variables=["air_temperature"],
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )
    assert list(ds.data_vars) == ["air_temperature"]
    # deployment-resolved position coordinates are structural, not filtered out
    assert "latitude" in ds.coords


@requires_mount
def test_build_dataset_is_idempotent_across_repeated_calls(db_session, config_provider, data_provider):
    first = build_dataset(
        "isfjord_radio_solar_park_measurements3",
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )
    second = build_dataset(
        "isfjord_radio_solar_park_measurements3",
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )
    assert first.sizes["time"] == second.sizes["time"]
    assert list(first["air_temperature"].values) == list(second["air_temperature"].values)


@requires_mount
def test_build_dataset_logs_start_and_end(db_session, config_provider, data_provider, caplog):
    build_dataset(
        "kapp_thordsen_10minute",
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )
    assert "building dataset kapp_thordsen_10minute" in caplog.text
    assert "built dataset kapp_thordsen_10minute" in caplog.text


def test_build_dataset_unknown_id_raises(db_session, config_provider, data_provider):
    with pytest.raises(DatasetConfigNotFoundError):
        build_dataset(
            "does_not_exist",
            session=db_session,
            config_provider=config_provider,
            data_provider=data_provider,
        )
