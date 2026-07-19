from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from open_csi_publisher.core.config_schema import (
    DatasetConfig,
    GenericCsvSourceConfig,
    LoggerNetSourceConfig,
)

LOGGERNET_CONFIG = {
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

GENERIC_CSV_CONFIG = {
    "id": "station_b",
    "source_type": "generic_csv",
    "access": "public",
    "source_config": {"file_path": "station_b/data.csv", "timestamp_column": "timestamp"},
    "variables": [{"raw_name": "temp", "standard_name": "air_temperature"}],
    "platform_type": "fixed",
    "deployments": [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6}],
    "metadata": {"title": "Station B"},
    "output": {"file_naming": "{station}.nc"},
}


def test_loggernet_config_resolves_to_loggernet_source_config():
    config = DatasetConfig.model_validate(LOGGERNET_CONFIG)
    assert isinstance(config.source_config, LoggerNetSourceConfig)
    assert config.source_config.file_pattern == "station_a/Table.dat"


def test_generic_csv_config_resolves_to_generic_csv_source_config():
    config = DatasetConfig.model_validate(GENERIC_CSV_CONFIG)
    assert isinstance(config.source_config, GenericCsvSourceConfig)
    assert config.source_config.file_path == "station_b/data.csv"


def test_generic_csv_source_config_default_timestamp_column():
    doc = copy.deepcopy(GENERIC_CSV_CONFIG)
    del doc["source_config"]["timestamp_column"]
    config = DatasetConfig.model_validate(doc)
    assert config.source_config.timestamp_column == "timestamp"


def test_loggernet_source_config_shape_rejected_under_generic_csv_type():
    doc = copy.deepcopy(GENERIC_CSV_CONFIG)
    doc["source_config"] = {"file_pattern": "station_a/Table.dat"}  # loggernet-shaped
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_generic_csv_source_config_shape_rejected_under_loggernet_type():
    doc = copy.deepcopy(LOGGERNET_CONFIG)
    doc["source_config"] = {"file_path": "x.csv"}  # generic_csv-shaped
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)


def test_unknown_source_type_rejected():
    doc = copy.deepcopy(LOGGERNET_CONFIG)
    doc["source_type"] = "satellite_feed"
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(doc)
