from __future__ import annotations

from fastapi import HTTPException

from open_csi_publisher.api.auth import User
from open_csi_publisher.core.config_schema import DatasetConfig


def is_visible(config: DatasetConfig, user: User | None) -> bool:
    return not (config.access == "restricted" and user is None)


def require_visible(config: DatasetConfig, user: User | None) -> None:
    """404, not 403: a restricted dataset must look identical to a nonexistent one
    to an unauthorized caller (implementation_plan.md §10 — invisible, not merely
    blocked)."""
    if not is_visible(config, user):
        raise HTTPException(status_code=404)
