from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from open_csi_publisher.api.deps import get_dataset_locations
from open_csi_publisher.api.opendap import build_opendap_app
from open_csi_publisher.api.routers import (
    auth,
    config_validator,
    dataset_detail,
    datasets_api,
    pages,
    publish,
)
from open_csi_publisher.core.builder import DatasetTooLargeError
from open_csi_publisher.core.timeouts import DatasetBuildTimeoutError
from open_csi_publisher.settings import settings
from open_csi_publisher.state.db import get_engine, run_migrations
from open_csi_publisher.api.deps import get_branding

_STATIC_DIR = Path(__file__).resolve().parent / "static"

_OIDC_FIELDS = ("oidc_issuer", "oidc_client_id", "oidc_client_secret", "session_secret_key")


def create_app() -> FastAPI:
    branding = get_branding()
    # Deliberately NOT FastAPI(root_path=...): that forces scope["root_path"]
    # on every request, which Starlette's Mount routing (StaticFiles /static,
    # the /opendap sub-app) accumulates across nesting levels and uses to
    # strip a prefix from the incoming path (get_route_path). That only works
    # when a proxy forwards the *full, unstripped* path and tells the app
    # out-of-band how much is prefix — not the far more common "proxy strips
    # the prefix before forwarding" setup this app targets, where the
    # incoming path never had the prefix to begin with. Under that mismatch,
    # nested Mounts 404 (confirmed against a minimal Starlette repro).
    # Settings.root_path is instead applied manually, only to outbound URLs
    # this app hands back to the browser (templates/JS/redirects/JSON) — see
    # settings.py's root_path docstring.
    app = FastAPI(title=branding.site_name)
    _register_exception_handlers(app)

    engine = get_engine(settings.database_url)
    run_migrations(settings.database_url, settings.base_dir)
    app.state.session_factory = sessionmaker(bind=engine)

    app.include_router(pages.router)
    app.include_router(datasets_api.router)
    app.include_router(dataset_detail.router)
    app.include_router(publish.router)
    app.include_router(auth.router)
    app.include_router(config_validator.router)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    opendap_app = build_opendap_app(
        session_factory=app.state.session_factory, locations=get_dataset_locations()
    )
    app.mount("/opendap", opendap_app)

    _configure_oidc_session(app)

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Guarantees every unhandled exception is logged through loguru — a sink
    confirmed to actually be configured — instead of relying on uvicorn's own
    default exception logging, which for reasons not fully explained by
    anything in this codebase has been observed to silently swallow a fast-
    failing 500 in production (zero log output, not even uvicorn's usual
    "Exception in ASGI application" traceback line). This makes that
    "undebuggable" failure mode moot regardless of its underlying cause.

    Starlette dispatches to the most-specific registered handler for a given
    exception's __mro__, so the catch-all Exception handler below doesn't
    interfere with FastAPI's own default HTTPException handling (used
    throughout, e.g. api/deps.py's 404s).

    A handler keyed on bare Exception (or 500) is installed on Starlette's
    ServerErrorMiddleware, not ExceptionMiddleware like the two typed
    handlers above — it builds the response the client actually receives,
    but Starlette then re-raises the original exception anyway so that
    whatever's running this ASGI app (uvicorn, or a test's
    TestClient(raise_server_exceptions=True)) still sees it too. That's
    intentional upstream behavior, not something to work around here.

    Only covers the main app — the /opendap sub-app (api/opendap.py) is a
    separately mounted ASGI app and isn't reached by handlers registered
    here; it does its own local error handling instead.
    """

    @app.exception_handler(DatasetBuildTimeoutError)
    async def _handle_build_timeout(request: Request, exc: DatasetBuildTimeoutError) -> JSONResponse:
        logger.error("dataset build timed out: {}", exc)
        return JSONResponse(status_code=504, content={"detail": str(exc)})

    @app.exception_handler(DatasetTooLargeError)
    async def _handle_too_large(request: Request, exc: DatasetTooLargeError) -> JSONResponse:
        logger.warning("dataset build rejected (too large): {}", exc)
        return JSONResponse(status_code=413, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled exception handling {} {}", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})


def _configure_oidc_session(app: FastAPI) -> None:
    """Register SessionMiddleware only when OIDC is fully configured. A partially
    configured setup (e.g. `oidc_issuer` set but `session_secret_key` missing) does
    not crash startup — it logs which field(s) are missing and leaves login
    disabled, identical to OIDC being entirely unconfigured (settings.oidc_issuer
    docstring / Settings.oidc_configured)."""
    if settings.oidc_configured:
        # path left at Starlette's own default ("/"), not settings.root_path:
        # this app's own routes are never actually served at the prefixed
        # path (see create_app()'s docstring — the proxy strips it before
        # forwarding), so a cookie scoped to ROOT_PATH would never round-trip
        # back to those routes. The browser still only ever sees this cookie
        # under the proxy's /ROOT_PATH origin either way.
        app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
    elif settings.oidc_issuer is not None:
        missing = [f for f in _OIDC_FIELDS if not getattr(settings, f)]
        logger.error(
            "OIDC is only partially configured (missing: {}) — login is disabled", missing
        )
