from __future__ import annotations

import hashlib
import json
from typing import Any

from open_csi_publisher.providers.base import ConfigProvider
from open_csi_publisher.providers.config.folder import DatasetConfigNotFoundError
from open_csi_publisher.providers.thingsboard_client import ThingsBoardClient

_CONFIG_ATTRIBUTE_KEY = "open-csi-publisher-config"


class ThingsBoardConfigProvider(ConfigProvider):
    """Dataset configs come from a ThingsBoard device's SERVER_SCOPE
    `open-csi-publisher-config` attribute, not a file — a device's *name* is
    this provider's dataset id, exactly mirroring FolderConfigProvider's
    filename-stem-as-id convention."""

    def __init__(self, client: ThingsBoardClient):
        self._client = client

    def list_dataset_ids(self) -> list[str]:
        return self._client.list_device_names_with_attribute(_CONFIG_ATTRIBUTE_KEY)

    def load_config(self, dataset_id: str) -> dict[str, Any]:
        raw = self._raw_attribute_value(dataset_id)
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)

    def config_hash(self, dataset_id: str) -> str:
        raw = self._raw_attribute_value(dataset_id)
        content = json.dumps(raw, sort_keys=True) if isinstance(raw, dict) else raw
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _raw_attribute_value(self, dataset_id: str) -> Any:
        device = self._client.get_device_by_name(dataset_id)
        if device is None:
            raise DatasetConfigNotFoundError(dataset_id)
        value = self._client.get_server_attribute(device["id"]["id"], _CONFIG_ATTRIBUTE_KEY)
        if value is None:
            raise DatasetConfigNotFoundError(dataset_id)
        return value
