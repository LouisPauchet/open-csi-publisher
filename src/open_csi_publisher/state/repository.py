from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.state.models import ConfigVersion, FileIndexEntry


def get_current_config_version(session: Session, dataset_id: str) -> ConfigVersion | None:
    stmt = (
        select(ConfigVersion)
        .where(ConfigVersion.dataset_id == dataset_id)
        .order_by(ConfigVersion.created_at.desc(), ConfigVersion.id.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def record_config_version(
    session: Session, dataset_id: str, hash_: str, content: dict[str, Any]
) -> ConfigVersion:
    version = ConfigVersion(dataset_id=dataset_id, hash=hash_, content=content)
    session.add(version)
    session.flush()
    return version


def list_file_index(session: Session, dataset_id: str) -> list[FileRecord]:
    stmt = select(FileIndexEntry).where(FileIndexEntry.dataset_id == dataset_id)
    return [_to_file_record(row) for row in session.scalars(stmt).all()]


def upsert_file_index_entry(session: Session, dataset_id: str, record: FileRecord) -> None:
    stmt = select(FileIndexEntry).where(
        FileIndexEntry.dataset_id == dataset_id,
        FileIndexEntry.file_name == record.file_name,
    )
    existing = session.scalars(stmt).first()
    if existing is None:
        session.add(
            FileIndexEntry(
                dataset_id=dataset_id,
                file_name=record.file_name,
                file_role=record.file_role,
                size=record.size,
                time_start=record.time_start,
                time_end=record.time_end,
                variables=record.variables,
                status=record.status,
            )
        )
    else:
        existing.file_role = record.file_role
        existing.size = record.size
        existing.time_start = record.time_start
        existing.time_end = record.time_end
        existing.variables = record.variables
        existing.status = record.status
    session.flush()


def _to_file_record(entry: FileIndexEntry) -> FileRecord:
    return FileRecord(
        file_name=entry.file_name,
        file_role=entry.file_role,  # type: ignore[arg-type]
        size=entry.size,
        time_start=entry.time_start,
        time_end=entry.time_end,
        variables=entry.variables,
        status=entry.status,  # type: ignore[arg-type]
    )
