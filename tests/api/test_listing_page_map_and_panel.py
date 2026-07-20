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


def test_listing_page_includes_leaflet_assets(client):
    body = client.get("/").text
    assert "/static/vendor/leaflet/leaflet.css" in body
    assert "/static/vendor/leaflet/leaflet.js" in body


def test_listing_page_includes_map_and_panel_containers(client):
    body = client.get("/").text
    assert 'id="map"' in body
    assert 'id="dataset-panel"' in body


def test_listing_page_includes_map_and_panel_scripts(client):
    body = client.get("/").text
    assert "/static/js/map.js" in body
    assert "/static/js/dataset_panel.js" in body


def test_fixed_dataset_rows_carry_lat_lon_for_the_map(client):
    body = client.get("/").text
    # the example fixed station's configured position
    assert 'data-id="kapp_thordsen_10minute"' in body
    assert 'data-lat="78.5"' in body
    assert 'data-lon="15.0"' in body


def test_mobile_dataset_row_has_no_lat_lon_attributes(client):
    body = client.get("/").text
    # crude but effective: find the hanna_resvoll row's opening tag and check
    # it doesn't carry data-lat (mobile position isn't config, so the
    # listing row can't embed it — map.js fetches a track for these instead)
    start = body.index('data-id="hanna_resvoll_10min"')
    row_tag_end = body.index(">", start)
    row_tag = body[max(0, start - 200) : row_tag_end]
    assert "data-lat" not in row_tag


def test_restricted_dataset_never_gets_a_marker_or_row_for_anonymous(client):
    body = client.get("/").text
    assert "restricted_station" not in body


def test_listing_table_shows_description_column_not_full_metadata(client):
    body = client.get("/").text
    assert "<th>Description</th>" in body
    # the real description text (kapp_thordsen_10minute) is shown...
    assert "Fixed automatic weather station recording wind" in body
    # ...but other metadata fields that used to be dumped into the row are
    # no longer rendered there (still present in data-meta for JS/filtering,
    # just not as visible table cells)
    assert "<th>Metadata</th>" not in body
    assert "standard_name_vocabulary:" not in body


def test_dataset_row_still_carries_full_metadata_for_the_panel_and_filters(client):
    body = client.get("/").text
    # data-meta is what dataset_panel.js and map.js read from — must still
    # carry every field (including description), just not rendered as a cell
    assert '"standard_name_vocabulary"' in body
    assert '"description"' in body
