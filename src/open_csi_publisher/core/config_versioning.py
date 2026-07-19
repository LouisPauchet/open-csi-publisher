from __future__ import annotations

from sqlalchemy.orm import Session

from open_csi_publisher.core.config_schema import DatasetConfig
from open_csi_publisher.providers.base import ConfigProvider
from open_csi_publisher.state import repository


def get_versioned_config(
    dataset_id: str, *, session: Session, config_provider: ConfigProvider
) -> DatasetConfig:
    """Lazy config versioning (implementation_plan.md §4.4): triggered on every
    call (dataset access), not polled. Only re-reads/re-validates the config file
    when its hash has actually changed since the last-known version; otherwise
    serves the already-snapshotted content. Standalone so both core/builder.py and
    the listing/search service can share this behavior without either forcing a
    data-provider read just to resolve metadata.
    """
    current_hash = config_provider.config_hash(dataset_id)
    current_version = repository.get_current_config_version(session, dataset_id)

    if current_version is None or current_version.hash != current_hash:
        content = config_provider.load_config(dataset_id)
        repository.record_config_version(session, dataset_id, current_hash, content)
    else:
        content = current_version.content

    return DatasetConfig.model_validate(content)
