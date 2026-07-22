from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from open_csi_publisher import settings as settings_module
from open_csi_publisher.api.app import create_app

from ..conftest import REPO_ROOT, requires_mount


def _use_throwaway_db(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        settings_module.settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}"
    )


def test_create_app_serves_static_files(tmp_path, monkeypatch):
    _use_throwaway_db(monkeypatch, tmp_path)
    client = TestClient(create_app())

    assert client.get("/static/css/site.css").status_code == 200
    assert client.get("/static/js/filter.js").status_code == 200
    assert client.get("/static/js/map.js").status_code == 200
    assert client.get("/static/vendor/leaflet/leaflet.js").status_code == 200
    assert client.get("/static/vendor/leaflet/leaflet.css").status_code == 200


@requires_mount
def test_create_app_wires_pages_and_api_routers(tmp_path, monkeypatch):
    _use_throwaway_db(monkeypatch, tmp_path)
    client = TestClient(create_app())

    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]

    api = client.get("/datasets")
    assert api.status_code == 200
    assert api.json()["total"] == 3

    detail = client.get("/datasets/hanna_resvoll_10min")
    assert detail.status_code == 200
    assert detail.json()["id"] == "hanna_resvoll_10min"

    opendap = client.get("/opendap/datasets/hanna_resvoll_10min/opendap.dds")
    assert opendap.status_code == 200
    assert "air_temperature" in opendap.text

    publish = client.get("/publish/datasets")
    assert publish.status_code == 401  # wired in and gated, no key supplied

    map_page = client.get("/map")
    assert map_page.status_code == 200


def _set_full_oidc_config(monkeypatch) -> None:
    monkeypatch.setattr(settings_module.settings, "oidc_issuer", "https://example.com/issuer")
    monkeypatch.setattr(settings_module.settings, "oidc_client_id", "client-id")
    monkeypatch.setattr(settings_module.settings, "oidc_client_secret", "client-secret")
    monkeypatch.setattr(settings_module.settings, "session_secret_key", "session-secret")


def test_create_app_does_not_register_session_middleware_by_default(tmp_path, monkeypatch):
    _use_throwaway_db(monkeypatch, tmp_path)
    app = create_app()
    assert not any(m.cls is SessionMiddleware for m in app.user_middleware)


def test_create_app_registers_session_middleware_when_oidc_fully_configured(tmp_path, monkeypatch):
    _use_throwaway_db(monkeypatch, tmp_path)
    _set_full_oidc_config(monkeypatch)
    app = create_app()
    assert any(m.cls is SessionMiddleware for m in app.user_middleware)


def test_create_app_skips_session_middleware_and_logs_when_oidc_partially_configured(
    tmp_path, monkeypatch, caplog
):
    _use_throwaway_db(monkeypatch, tmp_path)
    monkeypatch.setattr(settings_module.settings, "oidc_issuer", "https://example.com/issuer")
    monkeypatch.setattr(settings_module.settings, "oidc_client_id", None)
    monkeypatch.setattr(settings_module.settings, "oidc_client_secret", None)
    monkeypatch.setattr(settings_module.settings, "session_secret_key", None)

    app = create_app()

    assert not any(m.cls is SessionMiddleware for m in app.user_middleware)
    assert "oidc" in caplog.text.lower()


def test_create_app_resolves_templates_independently_of_process_cwd(tmp_path, monkeypatch):
    # a real deployment's sources/data paths are explicit config (absolute paths
    # via settings), not implicitly CWD-relative — set base_dir explicitly to
    # simulate that, then change CWD to prove template resolution (which must be
    # Path(__file__)-relative, not CWD-relative) still works regardless
    _use_throwaway_db(monkeypatch, tmp_path)
    monkeypatch.setattr(settings_module.settings, "base_dir", str(REPO_ROOT))
    monkeypatch.chdir(tmp_path)

    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert "UNIS AT Example Solar Park AWS" in response.text
