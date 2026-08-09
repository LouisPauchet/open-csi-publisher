from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from open_csi_publisher.api.access import require_visible
from open_csi_publisher.api.auth import User, get_current_user
from open_csi_publisher.api.deps import get_dataset_location, get_db_session
from open_csi_publisher.api.schemas import (
    DatasetDetail,
    DeploymentInfo,
    TimeCoverage,
    VariableDetail,
)
from open_csi_publisher.core.builder import build_dataset, build_dataset_summary
from open_csi_publisher.core.config_versioning import get_versioned_config
from open_csi_publisher.core.export import render_csv_with_metadata_header, to_wide_dataframe
from open_csi_publisher.sources import DatasetLocation

router = APIRouter()


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def get_dataset_detail(
    session: Session = Depends(get_db_session),
    location: DatasetLocation = Depends(get_dataset_location),
    user: User | None = Depends(get_current_user),
) -> DatasetDetail:
    config = get_versioned_config(
        location.dataset_id, session=session, config_provider=location.config_provider
    )
    require_visible(config, user)

    # Deliberately NOT the full dataset (unlike /data and the downloads,
    # which need real data and already accept an explicit start/end range to
    # bound it): this route has no start/end parameter at all and is hit on
    # every dataset page view, so for a station spanning hundreds of files
    # and 100+ GB of history, building everything just to report a time
    # range and a few attributes would be the single biggest resource risk
    # in the whole app. build_dataset_summary() stays cheap regardless of
    # dataset size — see its docstring (core/builder.py) for exactly what it
    # does and doesn't read.
    metadata, coverage_span = build_dataset_summary(
        location.dataset_id,
        session=session,
        config_provider=location.config_provider,
        data_provider=location.data_provider,
    )

    coverage = (
        TimeCoverage(start=coverage_span[0], end=coverage_span[1]) if coverage_span is not None else None
    )

    return DatasetDetail(
        id=config.id,
        title=config.metadata.title,
        metadata=metadata,
        platform_type=config.platform_type,
        access=config.access,
        variables=[
            VariableDetail(
                name=v.canonical_name, standard_name=v.standard_name, units=v.units, dtype=v.dtype
            )
            for v in config.variables
        ],
        deployments=[_to_deployment_info(d) for d in config.deployments],
        time_coverage=coverage,
    )


@router.get("/datasets/{dataset_id}/deployments", response_model=list[DeploymentInfo])
def get_dataset_deployments(
    session: Session = Depends(get_db_session),
    location: DatasetLocation = Depends(get_dataset_location),
    user: User | None = Depends(get_current_user),
) -> list[DeploymentInfo]:
    config = get_versioned_config(
        location.dataset_id, session=session, config_provider=location.config_provider
    )
    require_visible(config, user)
    return [_to_deployment_info(d) for d in config.deployments]


@router.get("/datasets/{dataset_id}/data")
def get_dataset_data(
    start: datetime | None = None,
    end: datetime | None = None,
    variables: list[str] | None = Query(default=None),
    format: Literal["json", "csv"] = "json",
    session: Session = Depends(get_db_session),
    location: DatasetLocation = Depends(get_dataset_location),
    user: User | None = Depends(get_current_user),
):
    config = get_versioned_config(
        location.dataset_id, session=session, config_provider=location.config_provider
    )
    require_visible(config, user)

    ds = build_dataset(
        location.dataset_id,
        start=start,
        end=end,
        variables=variables,
        session=session,
        config_provider=location.config_provider,
        data_provider=location.data_provider,
    )
    if format == "csv":
        return PlainTextResponse(render_csv_with_metadata_header(ds), media_type="text/csv")
    df = to_wide_dataframe(ds)
    return _json_safe(df.to_dict(orient="list"))


@router.get("/datasets/{dataset_id}/download.nc")
def download_dataset_netcdf(
    start: datetime | None = None,
    end: datetime | None = None,
    session: Session = Depends(get_db_session),
    location: DatasetLocation = Depends(get_dataset_location),
    user: User | None = Depends(get_current_user),
):
    config = get_versioned_config(
        location.dataset_id, session=session, config_provider=location.config_provider
    )
    require_visible(config, user)

    ds = build_dataset(
        location.dataset_id,
        start=start,
        end=end,
        session=session,
        config_provider=location.config_provider,
        data_provider=location.data_provider,
    )
    buffer = io.BytesIO()
    ds.to_netcdf(buffer, engine="h5netcdf")
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/x-netcdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_download_basename(location.dataset_id, start, end)}.nc"'
        },
    )


@router.get("/datasets/{dataset_id}/download.csv")
def download_dataset_csv(
    start: datetime | None = None,
    end: datetime | None = None,
    session: Session = Depends(get_db_session),
    location: DatasetLocation = Depends(get_dataset_location),
    user: User | None = Depends(get_current_user),
):
    config = get_versioned_config(
        location.dataset_id, session=session, config_provider=location.config_provider
    )
    require_visible(config, user)

    ds = build_dataset(
        location.dataset_id,
        start=start,
        end=end,
        session=session,
        config_provider=location.config_provider,
        data_provider=location.data_provider,
    )
    return PlainTextResponse(
        render_csv_with_metadata_header(ds),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{_download_basename(location.dataset_id, start, end)}.csv"'
        },
    )


def _to_deployment_info(deployment) -> DeploymentInfo:
    return DeploymentInfo(
        start=deployment.start,
        end=deployment.end,
        lat=deployment.lat,
        lon=deployment.lon,
        elevation=deployment.elevation,
        platform_name=deployment.platform_name,
    )


def _json_safe(records: dict[str, list[Any]]) -> dict[str, list[Any]]:
    # NaN isn't valid JSON (FastAPI's JSONResponse uses allow_nan=False); real
    # sensor data legitimately has gaps. pandas' own .where(cond, None) doesn't
    # help here — None assigned into a float64 column is silently cast back to
    # NaN, since float arrays can't hold None — so the substitution has to
    # happen at the plain-Python-list level, after to_dict() has already left
    # pandas' dtype constraints behind.
    return {key: [None if pd.isna(v) else v for v in values] for key, values in records.items()}


def _download_basename(dataset_id: str, start: datetime | None, end: datetime | None) -> str:
    if start is None and end is None:
        return f"{dataset_id}_full"
    start_part = start.strftime("%Y%m%d") if start else "start"
    end_part = end.strftime("%Y%m%d") if end else "end"
    return f"{dataset_id}_{start_part}_{end_part}"
