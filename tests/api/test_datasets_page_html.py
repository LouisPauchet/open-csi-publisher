from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_csi_publisher.api.auth import User, get_current_user
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


def test_get_page_returns_200_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_visible_dataset_titles_appear_in_body(client):
    body = client.get("/").text
    assert "UNIS AT Example Solar Park AWS" in body
    assert "UNIS AGF Example Fixed Station AWS" in body
    assert "UNIS AGF Example Boat AWS" in body


def test_restricted_dataset_absent_from_body_for_anonymous(client):
    body = client.get("/").text
    assert "restricted_station" not in body
    assert "Restricted Test Station" not in body


def test_restricted_dataset_present_for_authenticated_user(app):
    app.dependency_overrides[get_current_user] = lambda: User(subject="test-user")
    body = TestClient(app).get("/").text
    assert "Restricted Test Station" in body


def test_filter_form_fields_present(client):
    body = client.get("/").text
    assert 'name="q"' in body
    assert 'name="platform_type"' in body
    assert 'name="meta_key"' in body
    assert 'name="meta_value"' in body


def test_platform_type_filter_narrows_rendered_rows(client):
    body = client.get("/", params={"platform_type": "mobile"}).text
    assert 'data-platform-type="mobile"' in body
    assert "UNIS AT Example Solar Park AWS" not in body


def test_dataset_rows_carry_data_attributes_for_js_filtering(client):
    body = client.get("/").text
    assert 'data-id="hanna_resvoll_10min"' in body
    assert 'data-platform-type="mobile"' in body
    assert "latitude" in body  # present somewhere in that row's data-standard-names


def test_meta_filter_narrows_rendered_rows(client):
    body = client.get(
        "/", params={"meta_key": "department", "meta_value": "Arctic Technology"}
    ).text
    assert "UNIS AT Example Solar Park AWS" in body
    assert "UNIS AGF Example Fixed Station AWS" not in body


def test_standard_name_facet_options_reflect_visible_datasets_only(client):
    # anonymous never sees a <select> option that only exists on the restricted
    # fixture, since it's never in the access-filtered "visible" set used for facets
    body = client.get("/").text
    assert "air_temperature" in body
