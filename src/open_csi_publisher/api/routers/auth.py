from __future__ import annotations

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from open_csi_publisher.settings import settings

router = APIRouter(prefix="/auth")

_ENTRA_CLIENT_NAME = "entra"


def _oauth_client():
    """Registered fresh from current `settings` on every call, not cached at import
    time — settings can change between requests in tests (`monkeypatch`) and, in
    principle, across a live config reload, so this must never bake in stale
    client_id/secret/issuer values."""
    oauth = OAuth()
    oauth.register(
        name=_ENTRA_CLIENT_NAME,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return getattr(oauth, _ENTRA_CLIENT_NAME)


def _callback_url(request: Request) -> str:
    return str(request.base_url).rstrip("/") + router.prefix + "/callback"


@router.get("/login")
async def login(request: Request):
    """Redirect to Entra ID's authorization endpoint. 404s (not a dead link) when
    OIDC isn't fully configured — checked per-request, not at app-construction
    time, so it stays responsive to a settings change within one process
    (api/app.py's `_configure_oidc_session` docstring)."""
    if not settings.oidc_configured:
        raise HTTPException(status_code=404)
    client = _oauth_client()
    return await client.authorize_redirect(request, _callback_url(request))


@router.get("/callback")
async def auth_callback(request: Request):
    """Exchange the authorization code and establish the session. Identity comes
    from the OIDC userinfo endpoint (not raw ID-token claims): standard and
    OIDC-compliant, and it means this callback never needs to verify an ID
    token's JWT signature itself — the userinfo call already proves the access
    token (and therefore the code exchange) was genuine."""
    if not settings.oidc_configured:
        raise HTTPException(status_code=404)
    client = _oauth_client()
    token = await client.authorize_access_token(request)
    userinfo = await client.userinfo(token=token)
    request.session["user"] = {"subject": userinfo["sub"], "email": userinfo.get("email")}
    return RedirectResponse(url="/")
