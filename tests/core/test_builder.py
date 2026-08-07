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


def test_build_dataset_raises_timeout_error_when_read_range_hangs(db_session, config_provider, monkeypatch):
    import time
    from datetime import datetime

    from open_csi_publisher import settings as settings_module
    from open_csi_publisher.core.models import FileRecord
    from open_csi_publisher.core.timeouts import DatasetBuildTimeoutError
    from open_csi_publisher.providers.base import DataProvider

    monkeypatch.setattr(settings_module.settings, "dataset_build_timeout_seconds", 0.05)

    class HangingReadRangeProvider(DataProvider):
        """get_file_index() is deterministic/instant, so this test is isolated
        to read_range()'s own timeout wrapping — not a race against real I/O
        timing (which index refresh's timeout, covered separately by
        test_file_index_refresh.py, already depends on)."""

        def get_file_index(self, source_config, previous=()):
            return [
                FileRecord(
                    file_name="fake.dat",
                    file_role="live",
                    size=10,
                    time_start=datetime(2020, 1, 1),
                    time_end=datetime(2020, 1, 2),
                    variables=["air_pressure"],
                    status="active",
                )
            ]

        def read_range(self, *args, **kwargs):
            time.sleep(5)
            raise AssertionError("should have timed out before returning")

    with pytest.raises(DatasetBuildTimeoutError) as exc_info:
        build_dataset(
            "isfjord_radio_solar_park_measurements3",
            session=db_session,
            config_provider=config_provider,
            data_provider=HangingReadRangeProvider(),
        )
    assert "isfjord_radio_solar_park_measurements3" in str(exc_info.value)


# --- size cap (DatasetTooLargeError) ----------------------------------------------


class _StubDataProvider:
    """A minimal DataProvider whose get_file_index() returns a scripted set of
    FileRecords with a controlled `size` — enough to drive build_dataset()'s
    size-cap check without needing real (potentially huge) files. read_range()
    only needs to succeed when the cap doesn't reject the build first."""

    def __init__(self, files):
        self._files = files

    def get_file_index(self, source_config, previous=()):
        return self._files

    def read_range(self, source_config, files, start, end, variables=None):
        import xarray as xr

        return xr.Dataset(coords={"time": []})


def _oversized_loggernet_files():
    from open_csi_publisher.core.models import FileRecord

    return [
        FileRecord(
            file_name="huge.dat",
            file_role="live",
            size=10 * 1024**3,  # 10 GB
            time_start=datetime(2020, 1, 1),
            time_end=datetime(2020, 1, 2),
            variables=["air_pressure"],
            status="active",
        )
    ]


def test_build_dataset_raises_too_large_error_when_selected_files_exceed_cap(
    db_session, config_provider, monkeypatch
):
    from open_csi_publisher import settings as settings_module
    from open_csi_publisher.core.builder import DatasetTooLargeError

    monkeypatch.setattr(settings_module.settings, "max_dataset_build_bytes", 1024**3)  # 1 GB

    with pytest.raises(DatasetTooLargeError) as exc_info:
        build_dataset(
            "isfjord_radio_solar_park_measurements3",
            session=db_session,
            config_provider=config_provider,
            data_provider=_StubDataProvider(_oversized_loggernet_files()),
        )
    message = str(exc_info.value)
    assert "isfjord_radio_solar_park_measurements3" in message
    assert "start" in message and "end" in message  # points at the actual fix


def test_build_dataset_enforce_size_cap_false_bypasses_the_check(db_session, config_provider, monkeypatch):
    from open_csi_publisher import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "max_dataset_build_bytes", 1024**3)  # 1 GB

    ds = build_dataset(
        "isfjord_radio_solar_park_measurements3",
        session=db_session,
        config_provider=config_provider,
        data_provider=_StubDataProvider(_oversized_loggernet_files()),
        enforce_size_cap=False,
    )
    assert ds is not None


def test_human_bytes_formats_each_unit_band():
    from open_csi_publisher.core.builder import _human_bytes

    assert _human_bytes(500) == "500.0 B"
    assert _human_bytes(2 * 1024) == "2.0 KB"
    assert _human_bytes(3 * 1024**2) == "3.0 MB"
    assert _human_bytes(4 * 1024**3) == "4.0 GB"
    assert _human_bytes(5 * 1024**4) == "5.0 TB"
    assert _human_bytes(6 * 1024**5) == "6.0 PB"


@requires_mount
def test_build_dataset_under_the_cap_succeeds(db_session, config_provider, data_provider, monkeypatch):
    from open_csi_publisher import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "max_dataset_build_bytes", 1024**3)  # 1 GB, real files are tiny
    ds = build_dataset(
        "isfjord_radio_solar_park_measurements3",
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )
    assert ds.sizes["time"] > 0
