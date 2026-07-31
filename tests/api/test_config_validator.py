from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_csi_publisher.api.auth import get_current_user
from open_csi_publisher.api.routers.config_validator import router as config_validator_router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(config_validator_router)
    app.dependency_overrides[get_current_user] = lambda: None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _valid_config() -> dict:
    return {
        "id": "test_station",
        "source_type": "loggernet",
        "access": "public",
        "source_config": {"file_pattern": "Test/Test.dat"},
        "variables": [
            {"raw_name": "temp_Avg", "standard_name": "air_temperature", "units": "degC"},
        ],
        "platform_type": "fixed",
        "deployments": [{"start": "2020-01-01T00:00:00Z", "lat": 78.5, "lon": 15.0}],
        "metadata": {"title": "Test Station"},
        "output": {"file_naming": "{station}.nc"},
    }


# --- GET /config-validator ---------------------------------------------------


def test_page_renders_a_form_with_a_textarea_and_validate_button(client):
    response = client.get("/config-validator")
    assert response.status_code == 200
    body = response.text
    assert "<textarea" in body
    assert "Validate" in body


# --- POST /config-validator/validate ------------------------------------------


def test_valid_config_reports_valid_with_a_summary(client):
    response = client.post("/config-validator/validate", json=_valid_config())
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []
    summary = body["summary"]
    assert summary["id"] == "test_station"
    assert summary["title"] == "Test Station"
    assert summary["platform_type"] == "fixed"
    assert summary["access"] == "public"
    assert summary["source_type"] == "loggernet"
    assert len(summary["variables"]) == 1
    assert summary["variables"][0]["name"] == "air_temperature"
    assert len(summary["deployments"]) == 1


def test_missing_required_field_is_reported_as_an_error(client):
    config = _valid_config()
    del config["metadata"]

    response = client.post("/config-validator/validate", json=config)

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["summary"] is None
    assert any("metadata" in err for err in body["errors"])


def test_mobile_deployment_missing_platform_name_is_reported(client):
    # mobile platform deployments require platform_name — a rule only
    # DatasetConfig's own model_validator enforces, not a bare field type
    config = _valid_config()
    config["platform_type"] = "mobile"
    config["deployments"] = [{"start": "2020-01-01T00:00:00Z"}]

    response = client.post("/config-validator/validate", json=config)

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("platform_name" in err for err in body["errors"])


def test_malformed_json_body_is_reported_as_a_friendly_error(client):
    response = client.post(
        "/config-validator/validate",
        content="{not valid json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("json" in err.lower() for err in body["errors"])


def test_non_object_json_body_is_reported_as_an_error(client):
    response = client.post(
        "/config-validator/validate",
        content="[1, 2, 3]",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("object" in err.lower() for err in body["errors"])
