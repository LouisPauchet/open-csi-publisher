from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_csi_publisher.api.auth import get_current_user
from open_csi_publisher.api.deps import get_dataset_locations, get_db_session
from open_csi_publisher.api.routers.pages import router as pages_router


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
    app.include_router(pages_router)
    app.dependency_overrides[get_db_session] = _override_db_session(session_factory)
    app.dependency_overrides[get_dataset_locations] = lambda: locations
    app.dependency_overrides[get_current_user] = lambda: None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_get_map_page_returns_200_html(client):
    response = client.get("/map")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_map_page_includes_leaflet_assets(client):
    body = client.get("/map").text
    assert "/static/vendor/leaflet/leaflet.css" in body
    assert "/static/vendor/leaflet/leaflet.js" in body


def test_map_page_includes_map_container(client):
    body = client.get("/map").text
    assert 'id="map"' in body


def test_map_page_includes_own_script(client):
    body = client.get("/map").text
    assert "/static/js/map.js" in body
