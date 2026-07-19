from __future__ import annotations

import json

from open_csi_publisher.core.config_schema import DatasetConfig
from open_csi_publisher.core.config_versioning import get_versioned_config
from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.state import repository

CONFIG = {
    "id": "station_a",
    "source_type": "loggernet",
    "access": "public",
    "source_config": {"file_pattern": "station_a/Table.dat"},
    "variables": [{"raw_name": "AirT_C", "standard_name": "air_temperature"}],
    "platform_type": "fixed",
    "deployments": [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6}],
    "metadata": {"title": "Station A"},
    "output": {"file_naming": "{station}.nc"},
}


class CountingConfigProvider(FolderConfigProvider):
    def __init__(self, folder):
        super().__init__(folder)
        self.load_config_calls = 0

    def load_config(self, dataset_id: str):
        self.load_config_calls += 1
        return super().load_config(dataset_id)


def _write(tmp_path, content: dict) -> None:
    (tmp_path / "station_a.json").write_text(json.dumps(content), encoding="utf-8")


def test_first_access_snapshots_and_returns_validated_config(tmp_path, db_session):
    _write(tmp_path, CONFIG)
    provider = CountingConfigProvider(tmp_path)

    config = get_versioned_config("station_a", session=db_session, config_provider=provider)

    assert isinstance(config, DatasetConfig)
    assert config.id == "station_a"
    version = repository.get_current_config_version(db_session, "station_a")
    assert version is not None
    assert version.hash == provider.config_hash("station_a")


def test_unchanged_config_does_not_reload_or_resnapshot(tmp_path, db_session):
    _write(tmp_path, CONFIG)
    provider = CountingConfigProvider(tmp_path)

    get_versioned_config("station_a", session=db_session, config_provider=provider)
    assert provider.load_config_calls == 1

    get_versioned_config("station_a", session=db_session, config_provider=provider)
    assert provider.load_config_calls == 1  # served from the state store, not reloaded


def test_changed_config_records_a_new_version(tmp_path, db_session):
    _write(tmp_path, CONFIG)
    provider = CountingConfigProvider(tmp_path)

    get_versioned_config("station_a", session=db_session, config_provider=provider)
    first_version = repository.get_current_config_version(db_session, "station_a")

    changed = dict(CONFIG)
    changed["metadata"] = {"title": "Station A (renamed)"}
    _write(tmp_path, changed)

    config = get_versioned_config("station_a", session=db_session, config_provider=provider)
    assert provider.load_config_calls == 2
    assert config.metadata.title == "Station A (renamed)"

    second_version = repository.get_current_config_version(db_session, "station_a")
    assert second_version.hash != first_version.hash
