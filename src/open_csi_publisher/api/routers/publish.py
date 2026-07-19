from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from open_csi_publisher.api.deps import get_dataset_location, get_dataset_locations, get_db_session
from open_csi_publisher.core import builder as builder_module
from open_csi_publisher.core.builder import resolve_time_coverage
from open_csi_publisher.core.config_versioning import get_versioned_config
from open_csi_publisher.core.publish import (
    is_month_settled,
    latest_settled_month,
    month_bounds,
    render_file_naming,
)
from open_csi_publisher.index.service import refresh_and_get_index
from open_csi_publisher.settings import settings
from open_csi_publisher.sources import DatasetLocation
from open_csi_publisher.state import repository

router = APIRouter()


def require_api_key(request: Request) -> None:
    """A separate, simpler mechanism from get_current_user's OIDC session flow
    (implementation_plan.md §11): a small number of trusted server-to-server
    consumers, not end users — no session, no redirect flow."""
    auth_header = request.headers.get("authorization", "")
    key = auth_header[len("Bearer ") :] if auth_header.startswith("Bearer ") else None
    if key is None or key not in settings.publish_api_keys:
        raise HTTPException(status_code=401)


@router.get("/publish/datasets", dependencies=[Depends(require_api_key)])
def list_publishable_datasets(
    session: Session = Depends(get_db_session),
    locations: list[DatasetLocation] = Depends(get_dataset_locations),
) -> list[dict]:
    now = _now()
    results = []
    for location in locations:
        config = get_versioned_config(
            location.dataset_id, session=session, config_provider=location.config_provider
        )
        if not config.output.publish:
            continue

        index_entries = refresh_and_get_index(
            session, location.dataset_id, config.source_config, location.data_provider
        )
        period = latest_settled_month(resolve_time_coverage(index_entries), now=now)
        results.append(
            {
                "dataset_id": location.dataset_id,
                "latest_complete_month": period,
                "download_url": f"/publish/{location.dataset_id}/{period}" if period else None,
            }
        )
    return results


@router.get("/publish/{dataset_id}/{period}", dependencies=[Depends(require_api_key)])
def get_publish_month(
    dataset_id: str,
    period: str,
    session: Session = Depends(get_db_session),
    location: DatasetLocation = Depends(get_dataset_location),
) -> StreamingResponse:
    config = get_versioned_config(
        location.dataset_id, session=session, config_provider=location.config_provider
    )
    if not config.output.publish:
        raise HTTPException(status_code=404)

    year, month = _parse_period(period)

    # Immutability first (implementation_plan.md §4.4): once a month has been
    # generated it's served unconditionally, without re-checking settledness
    # or the current config — a deliberate, manual action would be needed to
    # regenerate it, which this endpoint never does on its own.
    existing = repository.get_publish_log_entry(session, dataset_id, period)
    if existing is not None:
        return _file_response(Path(existing.cached_file_path))

    index_entries = refresh_and_get_index(
        session, dataset_id, config.source_config, location.data_provider
    )
    coverage = resolve_time_coverage(index_entries)
    if not is_month_settled(year, month, coverage=coverage, now=_now()):
        raise HTTPException(status_code=409, detail="requested month is not yet complete")

    start, end = month_bounds(year, month)
    ds = builder_module.build_dataset(
        dataset_id,
        start=start,
        end=end,
        session=session,
        config_provider=location.config_provider,
        data_provider=location.data_provider,
    )
    # build_dataset() already attached processing_software_version/config_hash/
    # config_version_timestamp/history to every build (core/builder.py) — read
    # them back rather than re-querying, so there's no risk of this endpoint's
    # own lookup landing on a config version newer than the one actually baked
    # into the data it just built.
    software_version = ds.attrs["processing_software_version"]
    config_hash = ds.attrs["config_hash"]

    filename = render_file_naming(
        config.output.file_naming,
        station=config.id,
        table=config.source_config.table_name or "",
        year=year,
        month=month,
    )
    cache_dir = Path(settings.publish_cache_dir) / dataset_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_path = cache_dir / filename
    ds.to_netcdf(cached_path, engine="h5netcdf")

    repository.record_publish_log_entry(
        session,
        dataset_id=dataset_id,
        period=period,
        config_hash=config_hash,
        software_version=software_version,
        cached_file_path=str(cached_path),
    )

    return _file_response(cached_path)


def _file_response(path: Path) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(path.read_bytes()),
        media_type="application/x-netcdf",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


def _parse_period(period: str) -> tuple[int, int]:
    try:
        year_str, month_str = period.split("-")
        return int(year_str), int(month_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="period must be yyyy-mm") from None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
