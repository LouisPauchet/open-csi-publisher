from __future__ import annotations

import pytest
from starlette.requests import Request

from open_csi_publisher import settings as settings_module
from open_csi_publisher.api.auth import User, get_current_user


def _request(cookie_header: bytes | None = None, session: dict | None = None) -> Request:
    headers = [(b"cookie", cookie_header)] if cookie_header else []
    scope: dict = {"type": "http", "headers": headers}
    if session is not None:
        scope["session"] = session
    return Request(scope)


@pytest.fixture(autouse=True)
def no_oidc_configured(monkeypatch):
    monkeypatch.setattr(settings_module.settings, "oidc_issuer", None)


@pytest.mark.anyio
async def test_get_current_user_is_none_with_no_request_state():
    assert await get_current_user(_request()) is None


@pytest.mark.anyio
async def test_get_current_user_is_none_even_with_a_forged_session_cookie():
    # pins the "always anonymous while no OIDC provider is configured" contract,
    # so a later OIDC change can't silently start trusting an unverified cookie
    request = _request(cookie_header=b"session=forged-value; other=1")
    assert await get_current_user(request) is None


@pytest.fixture
def oidc_configured(monkeypatch):
    monkeypatch.setattr(settings_module.settings, "oidc_issuer", "https://example.com/issuer")
    monkeypatch.setattr(settings_module.settings, "oidc_client_id", "client-id")
    monkeypatch.setattr(settings_module.settings, "oidc_client_secret", "client-secret")
    monkeypatch.setattr(settings_module.settings, "session_secret_key", "session-secret")


@pytest.mark.anyio
async def test_get_current_user_resolves_user_from_existing_session_when_oidc_configured(
    oidc_configured,
):
    request = _request(session={"user": {"subject": "abc123", "email": "a@b.com"}})
    user = await get_current_user(request)
    assert user == User(subject="abc123", email="a@b.com")


@pytest.mark.anyio
async def test_get_current_user_is_none_when_oidc_configured_but_session_has_no_user(
    oidc_configured,
):
    request = _request(session={})
    assert await get_current_user(request) is None


@pytest.mark.anyio
async def test_get_current_user_ignores_session_user_when_oidc_only_partially_configured(
    monkeypatch,
):
    # oidc_issuer set but session_secret_key missing: oidc_configured is False, so
    # login must behave exactly as if unconfigured — anonymous, even with a
    # session that (however it got there) contains a user.
    monkeypatch.setattr(settings_module.settings, "oidc_issuer", "https://example.com/issuer")
    monkeypatch.setattr(settings_module.settings, "oidc_client_id", "client-id")
    monkeypatch.setattr(settings_module.settings, "oidc_client_secret", "client-secret")
    monkeypatch.setattr(settings_module.settings, "session_secret_key", None)

    request = _request(session={"user": {"subject": "abc123"}})
    assert await get_current_user(request) is None


@pytest.fixture
def anyio_backend():
    return "asyncio"
