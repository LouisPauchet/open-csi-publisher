from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.providers.base import DataProvider
from open_csi_publisher.state import repository


def refresh_and_get_index(
    session: Session,
    dataset_id: str,
    source_config: Any,
    data_provider: DataProvider,
) -> list[FileRecord]:
    """Lazy file-index refresh (implementation_plan.md §6): triggered on every call
    (dataset access), not polled. Loads whatever was previously persisted, hands it
    to the data provider as `previous` so closed/unchanged files are never
    reparsed, then persists whatever comes back as the new current state.
    """
    previous = repository.list_file_index(session, dataset_id)
    fresh = data_provider.get_file_index(source_config, previous=previous)
    for record in fresh:
        repository.upsert_file_index_entry(session, dataset_id, record)
    return fresh
