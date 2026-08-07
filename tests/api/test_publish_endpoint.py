from __future__ import annotations

from unittest.mock import patch

import pytest
import xarray as xr
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_csi_publisher import settings as settings_module
from open_csi_publisher.api.deps import get_dataset_locations, get_db_session
from open_csi_publisher.api.routers.publish import router as publish_router
from open_csi_publisher.core import builder as builder_module

from ..conftest import requires_mount

API_KEY = "test-publish-key"

# The example fixed station's real data starts 2023-08-11; September 2023 is
# fully covered, well before the real historical/live gap, so it's a safe
# "settled" month with actual data rows to exercise real NetCDF generation.
SETTLED_PERIOD = "2023-09"


def _override_db_session(session_factory):
    def _dep():
        session = session_factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    return _dep


@pytest.fixture(autouse=True)
def publish_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module.settings, "publish_cache_dir", str(tmp_path / "publish_cache"))
    monkeypatch.setattr(settings_module.settings, "publish_api_keys_raw", API_KEY)


@pytest.fixture
def app(locations, session_factory):
    app = FastAPI()
    app.include_router(publish_router)
    app.dependency_overrides[get_db_session] = _override_db_session(session_factory)
    app.dependency_overrides[get_dataset_locations] = lambda: locations
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _auth_headers(key: str = API_KEY) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


# --- auth -------------------------------------------------------------------


def test_openapi_schema_declares_bearer_auth_for_publish_endpoints(app):
    # Swagger UI only renders an "Authorize" button / per-endpoint lock icon
    # (i.e. somewhere to actually enter the API key from "Try it out") for a
    # dependency FastAPI recognizes as a security scheme (fastapi.security.*).
    # A plain `request: Request` header read, however correct at runtime,
    # produces no such affordance in the generated OpenAPI schema.
    schema = app.openapi()
    assert schema["components"]["securitySchemes"]
    datasets_op = schema["paths"]["/publish/datasets"]["get"]
    assert datasets_op.get("security")


@requires_mount
def test_missing_api_key_401(client):
    assert client.get("/publish/datasets").status_code == 401


@requires_mount
def test_wrong_api_key_401(client):
    response = client.get(
        f"/publish/kapp_thordsen_10minute/{SETTLED_PERIOD}", headers=_auth_headers("wrong-key")
    )
    assert response.status_code == 401


# --- GET /publish/datasets ---------------------------------------------------


@requires_mount
def test_publish_datasets_lists_only_publish_true_datasets(client):
    response = client.get("/publish/datasets", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    ids = {d["dataset_id"] for d in body}
    assert ids == {"kapp_thordsen_10minute"}


@requires_mount
def test_publish_datasets_reports_a_real_latest_complete_month(client):
    body = client.get("/publish/datasets", headers=_auth_headers()).json()
    entry = body[0]
    assert entry["latest_complete_month"] is not None
    assert entry["download_url"] == f"/publish/kapp_thordsen_10minute/{entry['latest_complete_month']}"


@requires_mount
def test_download_url_is_prefixed_with_the_configured_root_path(client, monkeypatch):
    monkeypatch.setattr(settings_module.settings, "root_path", "/csi-publisher")

    body = client.get("/publish/datasets", headers=_auth_headers()).json()

    entry = body[0]
    assert entry["download_url"] == (
        f"/csi-publisher/publish/kapp_thordsen_10minute/{entry['latest_complete_month']}"
    )


# --- GET /publish/{id}/{yyyy-mm} --------------------------------------------


@requires_mount
def test_unknown_dataset_404(client):
    response = client.get(f"/publish/does_not_exist/{SETTLED_PERIOD}", headers=_auth_headers())
    assert response.status_code == 404


@requires_mount
def test_non_publishable_dataset_404(client):
    # hanna_resvoll_10min has output.publish: false
    response = client.get("/publish/hanna_resvoll_10min/2026-06", headers=_auth_headers())
    assert response.status_code == 404


@requires_mount
def test_incomplete_month_409(client):
    # a month that clearly hasn't happened yet
    response = client.get("/publish/kapp_thordsen_10minute/2099-01", headers=_auth_headers())
    assert response.status_code == 409


@requires_mount
def test_generates_and_returns_valid_netcdf(client):
    response = client.get(
        f"/publish/kapp_thordsen_10minute/{SETTLED_PERIOD}", headers=_auth_headers()
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-netcdf"

    import io

    ds = xr.open_dataset(io.BytesIO(response.content), engine="h5netcdf")
    assert "air_temperature" in ds.data_vars
    assert ds.sizes["time"] > 0
    assert ds.attrs["config_hash"]
    assert ds.attrs["processing_software_version"]


@requires_mount
def test_publish_is_exempt_from_the_dataset_size_cap(client, monkeypatch):
    # The publish endpoint is already self-bounded to one calendar month per
    # call and is a trusted, API-key-gated server-to-server path — an
    # absurdly tiny cap (which would 413 any ordinary /download.nc request)
    # must not block it.
    monkeypatch.setattr(settings_module.settings, "max_dataset_build_bytes", 1)
    response = client.get(f"/publish/kapp_thordsen_10minute/{SETTLED_PERIOD}", headers=_auth_headers())
    assert response.status_code == 200


@requires_mount
def test_second_request_is_cached_not_regenerated(client):
    with patch.object(builder_module, "build_dataset", wraps=builder_module.build_dataset) as spy:
        first = client.get(f"/publish/kapp_thordsen_10minute/{SETTLED_PERIOD}", headers=_auth_headers())
        assert spy.call_count == 1
        second = client.get(f"/publish/kapp_thordsen_10minute/{SETTLED_PERIOD}", headers=_auth_headers())
        assert spy.call_count == 1  # not called again

    assert first.content == second.content


@requires_mount
def test_immutable_after_config_change(client, sample_config_dir):
    first = client.get(f"/publish/kapp_thordsen_10minute/{SETTLED_PERIOD}", headers=_auth_headers())
    assert first.status_code == 200

    config_path = sample_config_dir / "kapp_thordsen_10minute.json"
    original = config_path.read_text(encoding="utf-8")
    try:
        mutated = original.replace(
            '"title": "UNIS AGF Example Fixed Station AWS"', '"title": "Renamed Station"'
        )
        assert mutated != original
        config_path.write_text(mutated, encoding="utf-8")

        second = client.get(
            f"/publish/kapp_thordsen_10minute/{SETTLED_PERIOD}", headers=_auth_headers()
        )
        assert second.status_code == 200
        assert second.content == first.content  # the OLD generation, not regenerated
    finally:
        config_path.write_text(original, encoding="utf-8")
