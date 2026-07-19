from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker

from open_csi_publisher.api.routers import dataset_detail, datasets_api, pages
from open_csi_publisher.settings import settings
from open_csi_publisher.state.db import get_engine, init_db

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="UNIS Environmental Data Portal")

    engine = get_engine(settings.database_url)
    init_db(engine)
    app.state.session_factory = sessionmaker(bind=engine)

    app.include_router(pages.router)
    app.include_router(datasets_api.router)
    app.include_router(dataset_detail.router)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app
