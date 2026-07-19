from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import pytest
import xarray as xr
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_csi_publisher.api.auth import User, get_current_user
from open_csi_publisher.api.deps import get_dataset_locations, get_db_session
from open_csi_publisher.api.routers.dataset_detail import router as dataset_detail_router

# Generic data-touching tests deliberately use hanna_resvoll_10min (a single small
# live file, no archived twin) rather than isfjord_radio_solar_park_measurements3
# (whose real .dat.backup archive is 188MB): each test gets a fresh in-memory DB
# with no cross-test file-index caching, so repeatedly hitting a huge archived file
# across many tests here made the file take >10 minutes to run. Isfjord's specific
# features (extra_dimension pyranometer grouping, .backup classification) are
# already covered end-to-end in tests/core/test_builder.py and
# tests/loggernet/test_provider.py — no need to re-exercise them at the route level.


def _override_db_session(session_factory):
    def _dep():
        session = session_factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    return _dep


@pytest.fixture
def app(locations, session_factory):
    app = FastAPI()
    app.include_router(dataset_detail_router)
    app.dependency_overrides[get_db_session] = _override_db_session(session_factory)
    app.dependency_overrides[get_dataset_locations] = lambda: locations
    app.dependency_overrides[get_current_user] = lambda: None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# --- GET /datasets/{id} --------------------------------------------------------


def test_detail_returns_200_and_expected_shape(client):
    response = client.get("/datasets/kapp_thordsen_10minute")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "kapp_thordsen_10minute"
    assert body["title"] == "UNIS AGF Kapp Thordsen AWS"
    assert body["platform_type"] == "fixed"
    assert body["access"] == "public"
    names = {v["name"] for v in body["variables"]}
    assert "air_temperature" in names
    assert "MetSENS_Status" in names


def test_detail_time_coverage_matches_known_real_bounds(client):
    body = client.get("/datasets/kapp_thordsen_10minute").json()
    assert body["time_coverage"]["start"] is not None
    # Kapp Thordsen historical file starts well before the live file's known
    # end; just assert the range brackets the known live-file end boundary
    # from the fileset reconciliation tests, without over-pinning exact bounds.
    assert body["time_coverage"]["end"] >= "2026-07-17T11:30:00"


def test_detail_unknown_id_404(client):
    assert client.get("/datasets/does_not_exist").status_code == 404


def test_detail_restricted_dataset_404_for_anonymous(client):
    assert client.get("/datasets/restricted_station").status_code == 404


def test_detail_restricted_dataset_200_for_authenticated(app):
    app.dependency_overrides[get_current_user] = lambda: User(subject="u")
    client = TestClient(app)
    response = client.get("/datasets/restricted_station")
    assert response.status_code == 200
    assert response.json()["access"] == "restricted"


# --- GET /datasets/{id}/deployments ---------------------------------------------


def test_deployments_returns_fixed_station_position_windows(client):
    body = client.get("/datasets/kapp_thordsen_10minute/deployments").json()
    assert len(body) == 1
    assert body[0]["lat"] == 78.4567
    assert body[0]["lon"] == 15.3239
    assert body[0]["platform_name"] is None


def test_deployments_returns_mobile_platform_windows(client):
    body = client.get("/datasets/hanna_resvoll_10min/deployments").json()
    assert len(body) == 1
    assert body[0]["platform_name"] == "Hanna Resvoll"
    assert body[0]["lat"] is None


def test_deployments_404_for_restricted_anonymous(client):
    assert client.get("/datasets/restricted_station/deployments").status_code == 404


def test_deployments_200_for_restricted_authenticated(app):
    app.dependency_overrides[get_current_user] = lambda: User(subject="u")
    client = TestClient(app)
    response = client.get("/datasets/restricted_station/deployments")
    assert response.status_code == 200
    assert response.json()[0]["lat"] == 78.2


# --- GET /datasets/{id}/data -----------------------------------------------------


def test_data_json_default_format(client):
    response = client.get("/datasets/hanna_resvoll_10min/data")
    assert response.status_code == 200
    body = response.json()
    assert "time" in body
    assert "air_temperature" in body
    assert len(body["time"]) == len(body["air_temperature"])


def test_data_variables_param_restricts_output(client):
    body = client.get(
        "/datasets/hanna_resvoll_10min/data",
        params={"variables": "air_temperature"},
    ).json()
    assert "air_temperature" in body
    assert "relative_humidity" not in body


def test_data_csv_format_is_parseable(client):
    response = client.get(
        "/datasets/hanna_resvoll_10min/data", params={"format": "csv"}
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    df = pd.read_csv(io.StringIO(response.text))
    assert "air_temperature" in df.columns


def test_data_time_window_narrows_result(client):
    body = client.get(
        "/datasets/kapp_thordsen_10minute/data",
        params={"start": "2026-07-17T11:30:00", "end": "2026-07-18T00:00:00"},
    ).json()
    times = [datetime.fromisoformat(t) for t in body["time"]]
    assert min(times) >= datetime(2026, 7, 17, 11, 30, 0)
    assert max(times) <= datetime(2026, 7, 18, 0, 0, 0)


def test_data_404_for_restricted_anonymous(client):
    assert client.get("/datasets/restricted_station/data").status_code == 404


def test_data_200_for_restricted_authenticated(app):
    app.dependency_overrides[get_current_user] = lambda: User(subject="u")
    client = TestClient(app)
    response = client.get("/datasets/restricted_station/data")
    assert response.status_code == 200
    assert "air_temperature" in response.json()


# --- GET /datasets/{id}/download.nc and .csv -------------------------------------


def test_download_nc_round_trips_via_xarray(client):
    response = client.get("/datasets/hanna_resvoll_10min/download.nc")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-netcdf"
    assert "attachment" in response.headers["content-disposition"]

    ds = xr.open_dataset(io.BytesIO(response.content), engine="h5netcdf")
    assert "air_temperature" in ds.data_vars
    assert ds.sizes["time"] > 0


def test_download_csv_is_parseable(client):
    response = client.get("/datasets/hanna_resvoll_10min/download.csv")
    assert response.status_code == 200
    df = pd.read_csv(io.StringIO(response.text))
    assert "air_temperature" in df.columns


def test_download_nc_404_for_restricted_anonymous(client):
    assert client.get("/datasets/restricted_station/download.nc").status_code == 404
