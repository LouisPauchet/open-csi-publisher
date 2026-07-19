from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from open_csi_publisher.core.config_schema import DatasetConfig


@dataclass(frozen=True)
class DatasetSearchDocument:
    """A flattened, per-request view of a config built purely for listing/search
    (implementation_plan.md search/filtering design). Computed fresh per request
    rather than cached — see core/search_index.py's module docstring for why."""

    dataset_id: str
    access: Literal["public", "restricted"]
    platform_type: Literal["fixed", "mobile"]
    text_blob: str
    standard_names: set[str]
    metadata_kv: dict[str, str]


def build_search_document(config: DatasetConfig) -> DatasetSearchDocument:
    """Pure function of a DatasetConfig, deliberately: if scale ever demands a
    materialized/cached search index, the natural hook is the existing lazy
    config-versioning trigger (recompute + persist when config_hash changes) —
    this function's signature wouldn't need to change to add that later.
    """
    metadata_kv = {
        key: str(value)
        for key, value in config.metadata.model_dump().items()
        if value is not None
    }
    standard_names = {v.standard_name for v in config.variables if v.standard_name}
    text_blob = " ".join([config.id, *metadata_kv.values()]).lower()

    return DatasetSearchDocument(
        dataset_id=config.id,
        access=config.access,
        platform_type=config.platform_type,
        text_blob=text_blob,
        standard_names=standard_names,
        metadata_kv=metadata_kv,
    )
