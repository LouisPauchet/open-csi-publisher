from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.core.timeouts import run_with_timeout
from open_csi_publisher.providers.base import DataProvider
from open_csi_publisher.settings import settings
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

    The provider call itself is time-bounded (core/timeouts.py) — a stalled
    network-mounted file read (rclone/S3) or an unresponsive ThingsBoard API
    would otherwise block this indefinitely, with no response and no timeout.
    """
    previous = repository.list_file_index(session, dataset_id)
    fresh = run_with_timeout(
        data_provider.get_file_index,
        source_config,
        previous=previous,
        timeout=settings.dataset_build_timeout_seconds,
        description=f"file index refresh for dataset {dataset_id!r}",
    )
    for record in fresh:
        repository.upsert_file_index_entry(session, dataset_id, record)
    return fresh
