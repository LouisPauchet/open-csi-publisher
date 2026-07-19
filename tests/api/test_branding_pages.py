from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_csi_publisher import settings as settings_module
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


def test_listing_page_reflects_default_unis_branding(client):
    body = client.get("/").text
    assert "unis-logo-liggende.svg" in body
    assert "--brand-primary: #006199" in body
    assert '--brand-font: "IBM Plex Sans"' in body
    assert '--brand-heading-font: "Adamina"' in body


def test_map_page_reflects_default_unis_branding(client):
    body = client.get("/map").text
    assert "unis-logo-liggende.svg" in body
    assert "--brand-primary: #006199" in body


def test_listing_page_reflects_a_custom_branding_file(client, tmp_path, monkeypatch):
    branding_path = tmp_path / "branding.yaml"
    branding_path.write_text(
        "site_name: Acme Weather Portal\n"
        "logo_url: https://example.org/acme-logo.svg\n"
        "color_primary: '#ff6600'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module.settings, "base_dir", str(tmp_path))
    monkeypatch.setattr(settings_module.settings, "branding_file", "branding.yaml")

    body = client.get("/").text
    assert "Acme Weather Portal" in body
    assert "https://example.org/acme-logo.svg" in body
    assert "--brand-primary: #ff6600" in body
    # the default UNIS branding artifacts are gone — real dataset content that
    # happens to mention UNIS (it's the actual data source) legitimately stays
    assert "unis-logo-liggende.svg" not in body
    assert "--brand-primary: #006199" not in body


def test_listing_page_falls_back_to_generic_branding_when_file_absent(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings_module.settings, "base_dir", str(tmp_path))
    monkeypatch.setattr(settings_module.settings, "branding_file", "no_such_branding.yaml")

    body = client.get("/").text
    assert "unis-logo-liggende.svg" not in body
    assert "--brand-primary: #006199" not in body
