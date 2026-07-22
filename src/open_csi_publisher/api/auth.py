from __future__ import annotations

from pydantic import BaseModel
from starlette.requests import Request

from open_csi_publisher.settings import settings


class User(BaseModel):
    subject: str
    email: str | None = None


async def get_current_user(request: Request) -> User | None:
    """FastAPI dependency resolving the caller's identity from the session.

    With OIDC not fully configured (settings.oidc_configured is False — the
    default, and also the state of a partially-configured setup, see
    Settings.oidc_configured), this always returns None: every caller is
    anonymous, so restricted datasets stay hidden (implementation_plan.md
    §10). When configured, identity comes from the `user` claims dict the
    OIDC callback route (api/routers/auth.py) stored in the session on
    successful login — never re-verified here, since the session cookie
    itself is what's trusted (signed by SessionMiddleware, registered only
    when oidc_configured is True).
    """
    if not settings.oidc_configured:
        return None
    claims = request.session.get("user")
    if claims is None:
        return None
    return User(**claims)
