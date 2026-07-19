from __future__ import annotations

from pydantic import BaseModel
from starlette.requests import Request

from open_csi_publisher.settings import settings


class User(BaseModel):
    subject: str
    email: str | None = None


async def get_current_user(request: Request) -> User | None:
    """FastAPI dependency resolving the caller's identity from the session.

    With no OIDC provider configured (settings.oidc_issuer is None — the
    default), this always returns None: every caller is anonymous, so
    restricted datasets stay hidden (implementation_plan.md §10). This is the
    sole extension point future Entra ID/OIDC work will change: once wired in,
    a valid session cookie (set by an OIDC callback route not built in this
    phase) would resolve to a User here instead of an unconditional None.
    """
    if settings.oidc_issuer is None:
        return None
    return None  # placeholder branch, not implemented this phase
