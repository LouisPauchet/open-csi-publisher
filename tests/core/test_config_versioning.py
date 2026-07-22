from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from open_csi_publisher.core.config_versioning import get_versioned_config
from open_csi_publisher.providers.config.folder import FolderConfigProvider

VALID_CONFIG = {
    "id": "station_a",
    "source_type": "loggernet",
    "access": "public",
    "source_config": {"file_pattern": "station_a/*.dat*"},
    "variables": [{"raw_name": "AirT_C", "standard_name": "air_temperature"}],
    "platform_type": "fixed",
    "deployments": [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6}],
    "metadata": {"title": "Station A"},
    "output": {"file_naming": "{station}.nc"},
}


def _write(path, name: str, content: dict) -> None:
    (path / f"{name}.json").write_text(json.dumps(content), encoding="utf-8")


def test_get_versioned_config_logs_on_first_load(tmp_path, db_session, caplog):
    _write(tmp_path, "station_a", VALID_CONFIG)
    provider = FolderConfigProvider(tmp_path)

    get_versioned_config("station_a", session=db_session, config_provider=provider)

    assert "station_a" in caplog.text


def test_get_versioned_config_reuses_cached_version_when_hash_unchanged(tmp_path, db_session, caplog):
    _write(tmp_path, "station_a", VALID_CONFIG)
    provider = FolderConfigProvider(tmp_path)
    get_versioned_config("station_a", session=db_session, config_provider=provider)

    caplog.clear()
    get_versioned_config("station_a", session=db_session, config_provider=provider)

    assert "cache" in caplog.text.lower() or "cached" in caplog.text.lower()


def test_get_versioned_config_logs_dataset_id_on_validation_error(tmp_path, db_session, caplog):
    invalid = dict(VALID_CONFIG)
    del invalid["metadata"]  # required field
    _write(tmp_path, "station_a", invalid)
    provider = FolderConfigProvider(tmp_path)

    with pytest.raises(ValidationError):
        get_versioned_config("station_a", session=db_session, config_provider=provider)

    assert "station_a" in caplog.text
