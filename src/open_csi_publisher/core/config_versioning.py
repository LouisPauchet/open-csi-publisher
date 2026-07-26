from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from pydantic import ValidationError
from sqlalchemy.orm import Session

from open_csi_publisher.core.config_schema import DatasetConfig
from open_csi_publisher.providers.base import ConfigProvider
from open_csi_publisher.settings import settings
from open_csi_publisher.state import repository


def get_versioned_config(
    dataset_id: str,
    *,
    session: Session,
    config_provider: ConfigProvider,
    recheck_interval_seconds: float | None = None,
) -> DatasetConfig:
    """Lazy config versioning (implementation_plan.md §4.4): triggered on every
    call (dataset access), not polled. Only re-reads/re-validates the config file
    when its hash has actually changed since the last-known version; otherwise
    serves the already-snapshotted content. Standalone so both core/builder.py and
    the listing/search service can share this behavior without either forcing a
    data-provider read just to resolve metadata.

    `recheck_interval_seconds` (default: settings.config_recheck_interval_seconds)
    additionally throttles the hash check itself: within this window since the
    version was last verified, `config_provider.config_hash()` isn't called at
    all — for ThingsBoard-backed sources that's 2 HTTP calls avoided on every
    single dataset access, not just the reload/reparse those calls would have
    triggered.
    """
    if recheck_interval_seconds is None:
        recheck_interval_seconds = settings.config_recheck_interval_seconds

    current_version = repository.get_current_config_version(session, dataset_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if (
        current_version is not None
        and (now - current_version.last_checked_at).total_seconds() < recheck_interval_seconds
    ):
        logger.debug(
            "using cached config version for dataset {} (recheck window not yet elapsed)",
            dataset_id,
        )
        content = current_version.content
    else:
        current_hash = config_provider.config_hash(dataset_id)

        if current_version is None or current_version.hash != current_hash:
            logger.info(
                "loading and validating config for dataset {} (hash {})", dataset_id, current_hash
            )
            content = config_provider.load_config(dataset_id)
            repository.record_config_version(session, dataset_id, current_hash, content)
        else:
            logger.debug("using cached config version for dataset {} (hash unchanged)", dataset_id)
            content = current_version.content
            repository.touch_config_version(session, current_version)

    try:
        return DatasetConfig.model_validate(content)
    except ValidationError:
        logger.error("config for dataset {} failed validation", dataset_id)
        raise
