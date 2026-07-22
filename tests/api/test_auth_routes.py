from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from open_csi_publisher import settings as settings_module
from open_csi_publisher.api.app import create_app

ISSUER = "https://login.microsoftonline.com/tenant-id/v2.0"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
DISCOVERY_DOC = {
    "issuer": ISSUER,
    "authorization_endpoint": f"{ISSUER}/oauth2/v2.0/authorize",
    "token_endpoint": f"{ISSUER}/oauth2/v2.0/token",
    "userinfo_endpoint": f"{ISSUER}/oidc/userinfo",
    "jwks_uri": f"{ISSUER}/discovery/v2.0/keys",
}


def _use_throwaway_db(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        settings_module.settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}"
    )


def _set_full_oidc_config(monkeypatch) -> None:
    monkeypatch.setattr(settings_module.settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(settings_module.settings, "oidc_client_id", "client-id")
    monkeypatch.setattr(settings_module.settings, "oidc_client_secret", "client-secret")
    monkeypatch.setattr(settings_module.settings, "session_secret_key", "session-secret")


@respx.mock
def test_login_redirects_to_authorize_endpoint_with_client_id_and_redirect_uri(
    tmp_path, monkeypatch
):
    _use_throwaway_db(monkeypatch, tmp_path)
    _set_full_oidc_config(monkeypatch)
    respx.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json=DISCOVERY_DOC))

    client = TestClient(create_app())
    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert location.startswith(DISCOVERY_DOC["authorization_endpoint"])
    assert "client_id=client-id" in location
    assert "response_type=code" in location
    assert "redirect_uri=" in location


def test_login_is_404_when_oidc_not_configured(tmp_path, monkeypatch):
    _use_throwaway_db(monkeypatch, tmp_path)
    client = TestClient(create_app())

    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 404


def test_login_is_404_when_oidc_only_partially_configured(tmp_path, monkeypatch):
    _use_throwaway_db(monkeypatch, tmp_path)
    monkeypatch.setattr(settings_module.settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(settings_module.settings, "oidc_client_id", "client-id")
    monkeypatch.setattr(settings_module.settings, "oidc_client_secret", None)
    monkeypatch.setattr(settings_module.settings, "session_secret_key", None)
    client = TestClient(create_app())

    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 404


def _extract_state(location: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(location).query)["state"][0]


@respx.mock
def test_callback_exchanges_code_and_establishes_a_session(tmp_path, monkeypatch):
    _use_throwaway_db(monkeypatch, tmp_path)
    _set_full_oidc_config(monkeypatch)
    respx.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json=DISCOVERY_DOC))
    respx.post(DISCOVERY_DOC["token_endpoint"]).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "fake-access-token", "token_type": "Bearer", "expires_in": 3600},
        )
    )
    respx.get(DISCOVERY_DOC["userinfo_endpoint"]).mock(
        return_value=httpx.Response(200, json={"sub": "abc123", "email": "a@b.com"})
    )

    client = TestClient(create_app())
    login_response = client.get("/auth/login", follow_redirects=False)
    state = _extract_state(login_response.headers["location"])

    callback_response = client.get(
        "/auth/callback", params={"code": "fake-code", "state": state}, follow_redirects=False
    )

    assert callback_response.status_code in (302, 307)
    assert callback_response.headers["location"] == "/"
    assert client.cookies.get("session")
