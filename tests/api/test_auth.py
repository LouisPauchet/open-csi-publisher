from __future__ import annotations

import pytest
from starlette.requests import Request

from open_csi_publisher import settings as settings_module
from open_csi_publisher.api.auth import get_current_user


def _request(cookie_header: bytes | None = None) -> Request:
    headers = [(b"cookie", cookie_header)] if cookie_header else []
    return Request({"type": "http", "headers": headers})


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
def anyio_backend():
    return "asyncio"
