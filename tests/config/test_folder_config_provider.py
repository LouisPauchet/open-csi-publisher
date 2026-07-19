from __future__ import annotations

import json

import pytest

from open_csi_publisher.providers.config.folder import (
    DatasetConfigNotFoundError,
    FolderConfigProvider,
)

MINIMAL_CONFIG = {
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


def test_list_dataset_ids_returns_sorted_json_stems(tmp_path):
    _write(tmp_path, "station_b", MINIMAL_CONFIG)
    _write(tmp_path, "station_a", MINIMAL_CONFIG)
    provider = FolderConfigProvider(tmp_path)
    assert provider.list_dataset_ids() == ["station_a", "station_b"]


def test_list_dataset_ids_ignores_non_json_files(tmp_path):
    _write(tmp_path, "station_a", MINIMAL_CONFIG)
    (tmp_path / "notes.txt").write_text("not a config", encoding="utf-8")
    (tmp_path / "sources.yaml").write_text("sources: []", encoding="utf-8")
    provider = FolderConfigProvider(tmp_path)
    assert provider.list_dataset_ids() == ["station_a"]


def test_load_config_returns_parsed_dict(tmp_path):
    _write(tmp_path, "station_a", MINIMAL_CONFIG)
    provider = FolderConfigProvider(tmp_path)
    assert provider.load_config("station_a") == MINIMAL_CONFIG


def test_load_config_missing_dataset_raises(tmp_path):
    provider = FolderConfigProvider(tmp_path)
    with pytest.raises(DatasetConfigNotFoundError):
        provider.load_config("does_not_exist")


def test_config_hash_changes_when_content_changes(tmp_path):
    _write(tmp_path, "station_a", MINIMAL_CONFIG)
    provider = FolderConfigProvider(tmp_path)
    hash_before = provider.config_hash("station_a")

    changed = dict(MINIMAL_CONFIG)
    changed["metadata"] = {"title": "Station A (renamed)"}
    _write(tmp_path, "station_a", changed)

    hash_after = provider.config_hash("station_a")
    assert hash_before != hash_after


def test_config_hash_stable_for_unchanged_file(tmp_path):
    _write(tmp_path, "station_a", MINIMAL_CONFIG)
    provider = FolderConfigProvider(tmp_path)
    assert provider.config_hash("station_a") == provider.config_hash("station_a")
