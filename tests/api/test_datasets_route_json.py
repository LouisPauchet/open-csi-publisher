from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_csi_publisher.api.auth import User, get_current_user
from open_csi_publisher.api.deps import get_dataset_locations, get_db_session
from open_csi_publisher.api.routers.datasets_api import router as datasets_api_router
from open_csi_publisher.api.schemas import DatasetListResponse


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
    app.include_router(datasets_api_router)
    app.dependency_overrides[get_db_session] = _override_db_session(session_factory)
    app.dependency_overrides[get_dataset_locations] = lambda: locations
    app.dependency_overrides[get_current_user] = lambda: None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _ids(response) -> set[str]:
    return {d["id"] for d in response.json()["datasets"]}


def test_get_datasets_returns_200_and_validates_against_schema(client):
    response = client.get("/datasets")
    assert response.status_code == 200
    parsed = DatasetListResponse.model_validate(response.json())
    # 3 real stations + the public string_extra_dimension_station fixture
    assert parsed.total == 4


def test_restricted_dataset_absent_for_anonymous(client):
    response = client.get("/datasets")
    assert "restricted_station" not in _ids(response)


def test_restricted_dataset_present_for_authenticated_user(app):
    app.dependency_overrides[get_current_user] = lambda: User(subject="test-user")
    client = TestClient(app)
    response = client.get("/datasets")
    assert "restricted_station" in _ids(response)


def test_q_query_param_narrows_results(client):
    response = client.get("/datasets", params={"q": "isfjord"})
    assert _ids(response) == {"isfjord_radio_solar_park_measurements3"}


def test_platform_type_query_param_narrows_results(client):
    response = client.get("/datasets", params={"platform_type": "mobile"})
    assert _ids(response) == {"hanna_resvoll_10min"}


def test_repeatable_standard_name_query_param(client):
    response = client.get(
        "/datasets", params=[("standard_name", "latitude"), ("standard_name", "longitude")]
    )
    assert _ids(response) == {"hanna_resvoll_10min"}


def test_meta_dot_key_query_param_narrows_results(client):
    response = client.get("/datasets", params={"meta.department": "Arctic Technology"})
    assert _ids(response) == {"isfjord_radio_solar_park_measurements3"}
