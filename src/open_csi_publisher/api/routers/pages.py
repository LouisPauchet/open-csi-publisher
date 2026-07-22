from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from open_csi_publisher.api.auth import User, get_current_user
from open_csi_publisher.api.deps import get_branding, get_dataset_locations, get_db_session
from open_csi_publisher.api.services import list_visible_datasets
from open_csi_publisher.branding import BrandingConfig
from open_csi_publisher.settings import settings
from open_csi_publisher.sources import DatasetLocation

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/")
def datasets_page(
    request: Request,
    q: str | None = None,
    platform_type: str | None = None,
    standard_name: list[str] | None = Query(default=None),
    meta_key: str | None = None,
    meta_value: str | None = None,
    session: Session = Depends(get_db_session),
    locations: list[DatasetLocation] = Depends(get_dataset_locations),
    user: User | None = Depends(get_current_user),
    branding: BrandingConfig = Depends(get_branding),
):
    standard_name = standard_name or []
    meta_filters = [(meta_key, meta_value)] if meta_key and meta_value else []

    # Access-filtered but not query-filtered: the facet options a <select> offers
    # must never leak a value that only exists on a dataset this caller can't see.
    visible = list_visible_datasets(session, user, locations=locations)
    facet_standard_names = sorted({name for d in visible.datasets for name in d.standard_names})
    facet_meta_keys = sorted({key for d in visible.datasets for key in d.metadata})

    filtered = list_visible_datasets(
        session,
        user,
        locations=locations,
        q=q,
        platform_type=platform_type,
        standard_names=standard_name or None,
        meta_filters=meta_filters,
    )

    return templates.TemplateResponse(
        request,
        "datasets/list.html",
        {
            "datasets": filtered.datasets,
            "total": filtered.total,
            "facet_standard_names": facet_standard_names,
            "facet_meta_keys": facet_meta_keys,
            "filters": {
                "q": q or "",
                "platform_type": platform_type or "",
                "standard_name": standard_name,
                "meta_key": meta_key or "",
                "meta_value": meta_value or "",
            },
            "branding": branding,
            "user": user,
            "oidc_enabled": settings.oidc_configured,
        },
    )


@router.get("/map")
def map_page(
    request: Request,
    branding: BrandingConfig = Depends(get_branding),
    user: User | None = Depends(get_current_user),
):
    # No server-side dataset data to embed: static/js/map.js fetches /datasets
    # (and, per mobile dataset, /datasets/{id}/data) itself at runtime, reusing
    # the same access-controlled endpoints rather than duplicating that logic
    # here — a restricted dataset is excluded there exactly once already.
    return templates.TemplateResponse(
        request,
        "map.html",
        {"branding": branding, "user": user, "oidc_enabled": settings.oidc_configured},
    )
