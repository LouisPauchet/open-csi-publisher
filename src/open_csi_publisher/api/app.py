from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker

from open_csi_publisher.api.deps import get_dataset_locations
from open_csi_publisher.api.opendap import build_opendap_app
from open_csi_publisher.api.routers import dataset_detail, datasets_api, pages, publish
from open_csi_publisher.settings import settings
from open_csi_publisher.state.db import get_engine, init_db
from open_csi_publisher.api.deps import get_branding

_STATIC_DIR = Path(__file__).resolve().parent / "static"


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
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    opendap_app = build_opendap_app(
        session_factory=app.state.session_factory, locations=get_dataset_locations()
    )
    app.mount("/opendap", opendap_app)

    return app
