from __future__ import annotations

import json
from typing import Any

import pytest

from open_csi_publisher.providers.config.folder import DatasetConfigNotFoundError
from open_csi_publisher.providers.config.thingsboard import ThingsBoardConfigProvider


class FakeThingsBoardClient:
    """Hand-written fake exposing just the three ThingsBoardClient methods
    ThingsBoardConfigProvider calls — avoids re-mocking HTTP at this layer
    (that's covered by tests/providers/test_thingsboard_client.py)."""

    def __init__(self) -> None:
        self.names: list[str] = []
        self.devices: dict[str, dict[str, Any]] = {}
        self.attributes: dict[str, Any] = {}

    def list_device_names_with_attribute(self, key: str) -> list[str]:
        return self.names

    def get_device_by_name(self, name: str) -> dict[str, Any] | None:
        return self.devices.get(name)

    def get_server_attribute(self, device_id: str, key: str) -> Any | None:
        return self.attributes.get(device_id)


def test_list_dataset_ids_returns_client_discovery_result():
    client = FakeThingsBoardClient()
    client.names = ["station_a", "station_b"]
    provider = ThingsBoardConfigProvider(client)

    assert provider.list_dataset_ids() == ["station_a", "station_b"]


def test_load_config_parses_json_string_attribute():
    client = FakeThingsBoardClient()
    client.devices["station_a"] = {"id": {"id": "dev-1"}, "name": "station_a"}
    client.attributes["dev-1"] = '{"id": "station_a", "source_type": "thingsboard"}'
    provider = ThingsBoardConfigProvider(client)

    assert provider.load_config("station_a") == {"id": "station_a", "source_type": "thingsboard"}


def test_load_config_accepts_already_parsed_dict_attribute():
    client = FakeThingsBoardClient()
    client.devices["station_a"] = {"id": {"id": "dev-1"}, "name": "station_a"}
    client.attributes["dev-1"] = {"id": "station_a", "source_type": "thingsboard"}
    provider = ThingsBoardConfigProvider(client)

    assert provider.load_config("station_a") == {"id": "station_a", "source_type": "thingsboard"}


def test_config_hash_identical_for_string_and_equivalent_dict_value():
    client_str = FakeThingsBoardClient()
    client_str.devices["station_a"] = {"id": {"id": "dev-1"}, "name": "station_a"}
    client_str.attributes["dev-1"] = json.dumps({"b": 2, "a": 1}, sort_keys=True)

    client_dict = FakeThingsBoardClient()
    client_dict.devices["station_a"] = {"id": {"id": "dev-1"}, "name": "station_a"}
    client_dict.attributes["dev-1"] = {"a": 1, "b": 2}

    hash_str = ThingsBoardConfigProvider(client_str).config_hash("station_a")
    hash_dict = ThingsBoardConfigProvider(client_dict).config_hash("station_a")
    assert hash_str == hash_dict


def test_config_hash_stable_for_repeated_identical_value():
    client = FakeThingsBoardClient()
    client.devices["station_a"] = {"id": {"id": "dev-1"}, "name": "station_a"}
    client.attributes["dev-1"] = {"id": "station_a"}
    provider = ThingsBoardConfigProvider(client)

    assert provider.config_hash("station_a") == provider.config_hash("station_a")


def test_config_hash_differs_when_value_differs():
    client = FakeThingsBoardClient()
    client.devices["station_a"] = {"id": {"id": "dev-1"}, "name": "station_a"}
    provider = ThingsBoardConfigProvider(client)

    client.attributes["dev-1"] = {"id": "station_a", "access": "public"}
    hash_before = provider.config_hash("station_a")
    client.attributes["dev-1"] = {"id": "station_a", "access": "restricted"}
    hash_after = provider.config_hash("station_a")

    assert hash_before != hash_after


def test_config_hash_independent_of_dict_key_order():
    client1 = FakeThingsBoardClient()
    client1.devices["s"] = {"id": {"id": "d"}, "name": "s"}
    client1.attributes["d"] = {"a": 1, "b": 2}

    client2 = FakeThingsBoardClient()
    client2.devices["s"] = {"id": {"id": "d"}, "name": "s"}
    client2.attributes["d"] = {"b": 2, "a": 1}

    hash1 = ThingsBoardConfigProvider(client1).config_hash("s")
    hash2 = ThingsBoardConfigProvider(client2).config_hash("s")
    assert hash1 == hash2


def test_load_config_raises_not_found_for_unknown_device():
    provider = ThingsBoardConfigProvider(FakeThingsBoardClient())
    with pytest.raises(DatasetConfigNotFoundError):
        provider.load_config("missing")


def test_load_config_raises_not_found_when_attribute_missing():
    client = FakeThingsBoardClient()
    client.devices["station_a"] = {"id": {"id": "dev-1"}, "name": "station_a"}
    provider = ThingsBoardConfigProvider(client)
    with pytest.raises(DatasetConfigNotFoundError):
        provider.load_config("station_a")


def test_config_hash_raises_not_found_for_unknown_device():
    provider = ThingsBoardConfigProvider(FakeThingsBoardClient())
    with pytest.raises(DatasetConfigNotFoundError):
        provider.config_hash("missing")
