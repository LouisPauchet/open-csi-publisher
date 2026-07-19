from __future__ import annotations

from fastapi.testclient import TestClient

from open_csi_publisher import settings as settings_module
from open_csi_publisher.api.app import create_app

from ..conftest import REPO_ROOT


def _use_throwaway_db(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        settings_module.settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}"
    )


def test_create_app_serves_static_files(tmp_path, monkeypatch):
    _use_throwaway_db(monkeypatch, tmp_path)
    client = TestClient(create_app())

    assert client.get("/static/css/site.css").status_code == 200
    assert client.get("/static/js/filter.js").status_code == 200


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
    assert "UNIS AT Isfjord Radio Solar Park AWS" in response.text
