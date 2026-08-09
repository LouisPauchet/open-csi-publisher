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


def test_get_visualize_page_returns_200_html(client):
    response = client.get("/visualize")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_visualize_page_lists_visible_dataset_titles_as_options(client):
    body = client.get("/visualize").text
    assert "UNIS AT Example Solar Park AWS" in body
    assert "UNIS AGF Example Fixed Station AWS" in body
    assert "UNIS AGF Example Boat AWS" in body


def test_restricted_dataset_absent_from_select_for_anonymous(client):
    body = client.get("/visualize").text
    assert "restricted_station" not in body
    assert "Restricted Test Station" not in body


def test_restricted_dataset_present_for_authenticated_user(app):
    app.dependency_overrides[get_current_user] = lambda: User(subject="test-user")
    body = TestClient(app).get("/visualize").text
    assert "Restricted Test Station" in body


def test_visualize_page_includes_chartjs_and_own_script(client):
    body = client.get("/visualize").text
    assert "/static/vendor/chartjs/chart.umd.min.js" in body
    assert "/static/js/visualize.js" in body


def test_visualize_page_includes_zoom_plugin_after_chartjs(client):
    # The plugin auto-registers itself against window.Chart when its script
    # runs, so load order matters: chart.umd.min.js first, then the plugin.
    body = client.get("/visualize").text
    plugin_path = "/static/vendor/chartjs-plugin-zoom/chartjs-plugin-zoom.umd.min.js"
    assert plugin_path in body
    assert body.index("/static/vendor/chartjs/chart.umd.min.js") < body.index(plugin_path)
    assert body.index(plugin_path) < body.index("/static/js/visualize.js")


def test_visualize_page_includes_reset_zoom_button(client):
    body = client.get("/visualize").text
    assert 'id="viz-reset-zoom"' in body


def test_visualize_page_includes_dataset_select_and_chart_canvas(client):
    body = client.get("/visualize").text
    assert 'id="viz-dataset"' in body
    assert 'id="viz-chart"' in body


def test_visualize_page_preselects_dataset_from_query_param(client):
    body = client.get("/visualize", params={"dataset": "kapp_thordsen_10minute"}).text
    assert 'value="kapp_thordsen_10minute" selected' in body


def test_visualize_page_query_param_for_invisible_dataset_does_not_preselect(client):
    # anonymous can't see the restricted dataset, so ?dataset=restricted_station
    # must not leak a selection for it (it's simply absent from the <select> at all)
    body = client.get("/visualize", params={"dataset": "restricted_station"}).text
    assert "restricted_station" not in body


def test_visualize_page_query_param_for_unknown_dataset_does_not_error(client):
    response = client.get("/visualize", params={"dataset": "does_not_exist"})
    assert response.status_code == 200
