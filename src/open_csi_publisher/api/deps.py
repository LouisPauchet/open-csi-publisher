from __future__ import annotations

from pathlib import Path
from typing import Iterator

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.requests import Request

from open_csi_publisher.branding import BrandingConfig, load_branding
from open_csi_publisher.settings import settings
from open_csi_publisher.sources import DatasetLocation, list_all_datasets, load_sources


def get_db_session(request: Request) -> Iterator[Session]:
    """Yields a session from the session factory create_app() attaches to
    app.state at startup. Tests substitute a throwaway in-memory-sqlite-backed
    app.state.session_factory rather than overriding this function itself, so
    the same wiring path is exercised in tests and production.
    """
    session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def get_dataset_locations() -> list[DatasetLocation]:
    """Every dataset across every configured source (implementation_plan.md
    §4.1), re-derived per call — cheap, since it's just a small YAML read plus
    listing config filenames, not parsing config content (that stays behind
    the lazy config-versioning hash check)."""
    base_dir = Path(settings.base_dir)
    sources = load_sources(base_dir / settings.sources_file)
    return list_all_datasets(sources, base_dir=base_dir)


def get_dataset_location(
    dataset_id: str, locations: list[DatasetLocation] = Depends(get_dataset_locations)
) -> DatasetLocation:
    for location in locations:
        if location.dataset_id == dataset_id:
            return location
    raise HTTPException(status_code=404)


def get_branding() -> BrandingConfig:
    """Re-derived per call (cheap — a small YAML read), same as
    get_dataset_locations(), so settings.branding_file changes (e.g. in tests)
    take effect without restarting the process."""
    base_dir = Path(settings.base_dir)
    return load_branding(base_dir / settings.branding_file)
