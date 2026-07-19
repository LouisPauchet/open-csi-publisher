from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from open_csi_publisher.api.auth import User, get_current_user
from open_csi_publisher.api.deps import get_dataset_locations, get_db_session
from open_csi_publisher.api.schemas import DatasetListResponse
from open_csi_publisher.api.services import list_visible_datasets
from open_csi_publisher.sources import DatasetLocation

router = APIRouter()

_META_PREFIX = "meta."


@router.get("/datasets", response_model=DatasetListResponse)
def get_datasets(
    request: Request,
    q: str | None = None,
    platform_type: str | None = None,
    standard_name: list[str] | None = Query(default=None),
    session: Session = Depends(get_db_session),
    locations: list[DatasetLocation] = Depends(get_dataset_locations),
    user: User | None = Depends(get_current_user),
) -> DatasetListResponse:
    return list_visible_datasets(
        session,
        user,
        locations=locations,
        q=q,
        platform_type=platform_type,
        standard_names=standard_name,
        meta_filters=_parse_meta_filters(request),
    )


def _parse_meta_filters(request: Request) -> list[tuple[str, str]]:
    """`meta.<key>=<value>` query params are read as raw query params rather than
    declared FastAPI parameters, since the set of valid keys is open-ended by
    design (implementation_plan.md's arbitrary-metadata filter requirement)."""
    return [
        (key[len(_META_PREFIX):], value)
        for key, value in request.query_params.multi_items()
        if key.startswith(_META_PREFIX)
    ]
