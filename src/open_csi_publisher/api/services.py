from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger
from pydantic import ValidationError
from sqlalchemy.orm import Session

from open_csi_publisher.api.access import is_visible
from open_csi_publisher.api.auth import User
from open_csi_publisher.api.schemas import DatasetListResponse, DatasetSummary
from open_csi_publisher.core.config_schema import DatasetConfig
from open_csi_publisher.core.config_versioning import get_versioned_config
from open_csi_publisher.core.search_index import DatasetSearchDocument, build_search_document
from open_csi_publisher.sources import DatasetLocation


def list_visible_datasets(
    session: Session,
    user: User | None,
    *,
    locations: list[DatasetLocation],
    q: str | None = None,
    platform_type: str | None = None,
    standard_names: list[str] | None = None,
    meta_filters: list[tuple[str, str]] | None = None,
) -> DatasetListResponse:
    """The single choke point every listing route (JSON and HTML) calls.
    Restricted-dataset exclusion happens here, exactly once, before any
    search/filter logic runs — nothing downstream ever sees a restricted
    dataset for an anonymous caller (implementation_plan.md §10).

    A dataset whose config file is broken (invalid JSON or fails schema
    validation) is logged and skipped, not allowed to fail the whole
    listing — one bad config file must not take every other dataset down
    with it.
    """
    summaries: list[DatasetSummary] = []
    for location in locations:
        try:
            config = get_versioned_config(
                location.dataset_id, session=session, config_provider=location.config_provider
            )
        except (ValidationError, json.JSONDecodeError):
            logger.error(
                "skipping dataset {} from listing: config is invalid", location.dataset_id
            )
            continue
        if not is_visible(config, user):
            continue

        doc = build_search_document(config)
        if not _matches(doc, q, platform_type, standard_names, meta_filters):
            continue

        summaries.append(_to_summary(config, doc))

    summaries.sort(key=lambda summary: summary.id)
    return DatasetListResponse(datasets=summaries, total=len(summaries))


def _matches(
    doc: DatasetSearchDocument,
    q: str | None,
    platform_type: str | None,
    standard_names: list[str] | None,
    meta_filters: list[tuple[str, str]] | None,
) -> bool:
    if q and q.lower() not in doc.text_blob:
        return False
    if platform_type and doc.platform_type != platform_type:
        return False
    if standard_names and not set(standard_names) <= doc.standard_names:
        return False
    if meta_filters:
        for key, value in meta_filters:
            actual = doc.metadata_kv.get(key)
            if actual is None or value.lower() not in actual.lower():
                return False
    return True


def _to_summary(config: DatasetConfig, doc: DatasetSearchDocument) -> DatasetSummary:
    metadata = {k: v for k, v in config.metadata.model_dump().items() if v is not None}
    return DatasetSummary(
        id=config.id,
        title=config.metadata.title,
        institution=config.metadata.institution,
        platform_type=config.platform_type,
        standard_names=sorted(doc.standard_names),
        metadata=metadata,
        position=_resolve_current_position(config),
    )


def _resolve_current_position(config: DatasetConfig) -> dict[str, float | None] | None:
    if config.platform_type != "fixed":
        return None  # mobile position is data, not config; deferred to the map-view slice

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    current = next(
        (d for d in config.deployments if d.start <= now and (d.end is None or d.end > now)),
        None,
    )
    dep = current or config.deployments[-1]
    return {"lat": dep.lat, "lon": dep.lon, "elevation": dep.elevation}
