from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from open_csi_publisher.api.deps import get_dataset_locations
from open_csi_publisher.api.opendap import build_opendap_app
from open_csi_publisher.api.routers import auth, dataset_detail, datasets_api, pages, publish
from open_csi_publisher.settings import settings
from open_csi_publisher.state.db import get_engine, init_db
from open_csi_publisher.api.deps import get_branding

_STATIC_DIR = Path(__file__).resolve().parent / "static"

_OIDC_FIELDS = ("oidc_issuer", "oidc_client_id", "oidc_client_secret", "session_secret_key")


def create_app() -> FastAPI:
    branding = get_branding()
    app = FastAPI(title=branding.site_name)

    engine = get_engine(settings.database_url)
    init_db(engine)
    app.state.session_factory = sessionmaker(bind=engine)

    app.include_router(pages.router)
    app.include_router(datasets_api.router)
    app.include_router(dataset_detail.router)
    app.include_router(publish.router)
    app.include_router(auth.router)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    opendap_app = build_opendap_app(
        session_factory=app.state.session_factory, locations=get_dataset_locations()
    )
    app.mount("/opendap", opendap_app)

    _configure_oidc_session(app)

    return app


def _configure_oidc_session(app: FastAPI) -> None:
    """Register SessionMiddleware only when OIDC is fully configured. A partially
    configured setup (e.g. `oidc_issuer` set but `session_secret_key` missing) does
    not crash startup — it logs which field(s) are missing and leaves login
    disabled, identical to OIDC being entirely unconfigured (settings.oidc_issuer
    docstring / Settings.oidc_configured)."""
    if settings.oidc_configured:
        app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
    elif settings.oidc_issuer is not None:
        missing = [f for f in _OIDC_FIELDS if not getattr(settings, f)]
        logger.error(
            "OIDC is only partially configured (missing: {}) — login is disabled", missing
        )
