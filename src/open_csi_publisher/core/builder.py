from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import version as _package_version
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from sqlalchemy.orm import Session

from open_csi_publisher.core.config_schema import DatasetConfig, VariableSpec
from open_csi_publisher.core.config_versioning import get_versioned_config
from open_csi_publisher.core.deployment import apply_deployment_metadata
from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.core.variable_mapping import apply_variable_spec
from open_csi_publisher.index.service import refresh_and_get_index
from open_csi_publisher.providers.base import ConfigProvider, DataProvider
from open_csi_publisher.state import repository


def build_dataset(
    dataset_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    variables: list[str] | None = None,
    *,
    session: Session,
    config_provider: ConfigProvider,
    data_provider: DataProvider,
) -> xr.Dataset:
    """The one function every consumer (REST, OPeNDAP, downloads, the publish
    endpoint) calls (implementation_plan.md §7): resolves the current config
    version, lazily refreshes the file index, reads only the raw columns and
    files actually needed, maps them to canonical variable names, resolves
    fixed/mobile deployment metadata, and attaches CF-ish global attributes.
    """
    start = _naive_utc(start)
    end = _naive_utc(end)

    config = get_versioned_config(dataset_id, session=session, config_provider=config_provider)

    index_entries = refresh_and_get_index(session, dataset_id, config.source_config, data_provider)
    selected = _select_files_covering(index_entries, start, end)

    raw_columns = _resolve_raw_columns_needed(config.variables, variables)
    raw = data_provider.read_range(
        config.source_config, files=selected, start=start, end=end, variables=raw_columns
    )

    mapped = apply_variable_spec(raw, config.variables)
    if variables is not None:
        mapped = mapped[[name for name in variables if name in mapped.data_vars]]

    result = apply_deployment_metadata(mapped, config)
    result.attrs.update(_build_global_attrs(config))
    result.attrs.update(_build_provenance_attrs(session, dataset_id, config))
    result.attrs.update(_build_coverage_attrs(result))
    return result


def _naive_utc(value: datetime | None) -> datetime | None:
    # Raw LoggerNet timestamps carry no timezone and are treated as UTC by
    # convention. A caller-supplied start/end can arrive timezone-aware — a
    # REST query param like "?start=2026-07-17T11:30:00.000Z" (exactly what
    # JS's Date.toISOString() produces) is parsed by FastAPI/pydantic into an
    # aware datetime — so it's converted to UTC and made naive here, the same
    # convention already used for Deployment.start/end
    # (core/config_schema.py), so it compares directly against the naive
    # file-index/`time` coordinate instead of raising a naive-vs-aware
    # TypeError.
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _select_files_covering(
    index_entries: list[FileRecord], start: datetime | None, end: datetime | None
) -> list[FileRecord]:
    selected = []
    for entry in index_entries:
        if entry.time_start is None or entry.time_end is None:
            continue  # nothing parsed yet (e.g. a brand-new, still-empty live file)
        if start is not None and entry.time_end < start:
            continue
        if end is not None and entry.time_start > end:
            continue
        selected.append(entry)
    return selected


def _resolve_raw_columns_needed(
    variable_specs: list[VariableSpec], requested_canonical: list[str] | None
) -> list[str]:
    if requested_canonical is None:
        specs = variable_specs
    else:
        wanted = set(requested_canonical)
        specs = [spec for spec in variable_specs if spec.canonical_name in wanted]

    raw_names: list[str] = []
    for spec in specs:
        raw_names.extend(spec.all_raw_names())
    return raw_names


def resolve_time_coverage(
    index_entries: list[FileRecord],
) -> tuple[datetime, datetime] | None:
    """Overall observed time range across a dataset's file index, or None if no
    file has any data yet (e.g. a brand-new, still-empty live file)."""
    starts = [e.time_start for e in index_entries if e.time_start is not None]
    ends = [e.time_end for e in index_entries if e.time_end is not None]
    if not starts or not ends:
        return None
    return min(starts), max(ends)


def _build_global_attrs(config: DatasetConfig) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        k: v for k, v in config.metadata.model_dump().items() if v is not None
    }
    # Not "id": ACDD reserves that (+ "naming_authority", already a settable
    # MetadataSpec field) for whichever downstream system formally
    # publishes/archives this data and assigns its own citable identifier —
    # our internal dataset slug would collide with that if it claimed "id"
    # itself.
    attrs["unis_id"] = config.id
    attrs["platform_type"] = config.platform_type
    attrs["source_type"] = config.source_type
    return attrs


def _build_coverage_attrs(ds: xr.Dataset) -> dict[str, Any]:
    """ACDD-style geospatial/temporal coverage attributes, computed from the
    actual built dataset — so they reflect any start/end/variables narrowing
    a caller applied, not the file index's overall span (see
    resolve_time_coverage() for that). Omitted rather than erroring when
    time is empty (e.g. a query window with no data) or latitude/longitude
    isn't present (e.g. narrowed away by a `variables` filter, or a mobile
    dataset whose config never mapped position columns) — the same
    "missing data is silently absent, not an error" convention used
    throughout this pipeline.
    """
    attrs: dict[str, Any] = {}

    time_values = ds["time"].values
    if time_values.size > 0:
        start = pd.Timestamp(time_values.min())
        end = pd.Timestamp(time_values.max())
        attrs["time_coverage_start"] = f"{start.isoformat()}Z"
        attrs["time_coverage_end"] = f"{end.isoformat()}Z"

    for name, min_key, max_key in (
        ("latitude", "geospatial_lat_min", "geospatial_lat_max"),
        ("longitude", "geospatial_lon_min", "geospatial_lon_max"),
    ):
        if name not in ds.variables:
            continue
        values = ds[name].values.astype("float64")
        if values.size and not np.all(np.isnan(values)):
            attrs[min_key] = float(np.nanmin(values))
            attrs[max_key] = float(np.nanmax(values))

    return attrs


def _build_provenance_attrs(session: Session, dataset_id: str, config: DatasetConfig) -> dict[str, Any]:
    """Attached to every build, not just the publish endpoint: which
    application version and which config version produced this data. The
    publish endpoint's cached files bake these in permanently (the file
    itself never changes after being written); live queries always reflect
    the current-best values at request time.
    """
    config_version = repository.get_current_config_version(session, dataset_id)
    software_version = _package_version("open-csi-publisher")
    generated_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    return {
        "processing_software_version": software_version,
        "config_hash": config_version.hash,
        "config_version_timestamp": config_version.created_at.isoformat(),
        "history": (
            f"{generated_at}Z: generated by open_csi_publisher {software_version} "
            f"for dataset '{dataset_id}' using config version {config_version.hash[:12]}"
        ),
    }
