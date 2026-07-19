from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ConfigVersion(Base):
    """A snapshot of a dataset config's content at the moment its hash changed
    (implementation_plan.md §4.4). "Current" is simply the most recent row per
    dataset_id — no separate flag/column, so there's nothing to un-set on write."""

    __tablename__ = "config_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True)
    hash: Mapped[str] = mapped_column(String)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FileIndexEntry(Base):
    """One raw source file's tracked state (implementation_plan.md §6), keyed by
    (dataset_id, file_name)."""

    __tablename__ = "file_index"
    __table_args__ = (UniqueConstraint("dataset_id", "file_name", name="uq_file_index_dataset_file"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True)
    file_name: Mapped[str] = mapped_column(String)
    file_role: Mapped[str] = mapped_column(String)
    size: Mapped[int] = mapped_column(Integer)
    time_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    time_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    variables: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String)
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PublishLog(Base):
    """Schema created now per implementation_plan.md §12; unused until the
    publish-endpoint phase (§14 step 11)."""

    __tablename__ = "publish_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True)
    period: Mapped[str] = mapped_column(String)
    config_hash: Mapped[str] = mapped_column(String)
    software_version: Mapped[str] = mapped_column(String)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    cached_file_path: Mapped[str] = mapped_column(String)
