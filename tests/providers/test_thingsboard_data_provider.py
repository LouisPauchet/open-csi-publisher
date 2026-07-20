from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from open_csi_publisher.core.config_schema import ThingsBoardSourceConfig
from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.providers.data.thingsboard.provider import ThingsBoardDataProvider

SOURCE_CONFIG = ThingsBoardSourceConfig(device_name="station_a")


def _dt_from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


class FakeThingsBoardClient:
    def __init__(self) -> None:
        self.devices: dict[str, dict[str, Any]] = {}
        self.latest: dict[str, dict[str, tuple[int, Any]]] = {}
        self.timeseries_response: dict[str, list[tuple[int, Any]]] = {}
        self.timeseries_calls: list[dict[str, Any]] = []

    def get_device_by_name(self, name: str) -> dict[str, Any] | None:
        return self.devices.get(name)

    def get_latest_telemetry(self, device_id: str) -> dict[str, tuple[int, Any]]:
        return self.latest.get(device_id, {})

    def get_timeseries(self, device_id, keys, start_ms, end_ms):
        self.timeseries_calls.append(
            {"device_id": device_id, "keys": keys, "start_ms": start_ms, "end_ms": end_ms}
        )
        return self.timeseries_response


def _register_device(client: FakeThingsBoardClient, created_ms: int = 1_700_000_000_000) -> None:
    client.devices["station_a"] = {
        "id": {"id": "dev-1", "entityType": "DEVICE"},
        "name": "station_a",
        "createdTime": created_ms,
    }


def test_get_file_index_initial_discovery_seeds_from_created_time():
    client = FakeThingsBoardClient()
    _register_device(client)
    client.latest["dev-1"] = {"temp": (1_700_003_600_000, 5.5), "status": (1_700_003_600_000, "ok")}
    provider = ThingsBoardDataProvider(client)

    records = provider.get_file_index(SOURCE_CONFIG)

    assert len(records) == 1
    record = records[0]
    assert record.file_role == "live"
    assert record.status == "active"
    assert record.size == 1_700_003_600_000
    assert record.time_start == _dt_from_ms(1_700_000_000_000)
    assert record.time_end == _dt_from_ms(1_700_003_600_000)
    assert set(record.variables) == {"temp", "status"}


def test_get_file_index_unchanged_latest_flips_active_to_closed():
    client = FakeThingsBoardClient()
    _register_device(client)
    client.latest["dev-1"] = {"temp": (1_700_003_600_000, 5.5)}
    provider = ThingsBoardDataProvider(client)

    first = provider.get_file_index(SOURCE_CONFIG)
    second = provider.get_file_index(SOURCE_CONFIG, previous=first)

    assert second[0].status == "closed"
    assert second[0].size == first[0].size


def test_get_file_index_reused_when_still_unchanged():
    client = FakeThingsBoardClient()
    _register_device(client)
    client.latest["dev-1"] = {"temp": (1_700_003_600_000, 5.5)}
    provider = ThingsBoardDataProvider(client)

    first = provider.get_file_index(SOURCE_CONFIG)
    closed = provider.get_file_index(SOURCE_CONFIG, previous=first)
    # a further refresh with an unchanged latest snapshot returns
    # content-identical reuse — not "zero extra HTTP calls" the way
    # generic_csv/loggernet avoid local reparsing: there's no signal cheaper
    # than one telemetry call for a remote source like ThingsBoard.
    third = provider.get_file_index(SOURCE_CONFIG, previous=closed)

    assert third[0] == closed[0]


def test_get_file_index_changed_latest_value_flips_back_to_active():
    client = FakeThingsBoardClient()
    _register_device(client)
    client.latest["dev-1"] = {"temp": (1_700_003_600_000, 5.5)}
    provider = ThingsBoardDataProvider(client)

    first = provider.get_file_index(SOURCE_CONFIG)
    closed = provider.get_file_index(SOURCE_CONFIG, previous=first)

    client.latest["dev-1"] = {"temp": (1_700_007_200_000, 6.0)}
    refreshed = provider.get_file_index(SOURCE_CONFIG, previous=closed)

    assert refreshed[0].status == "active"
    assert refreshed[0].size == 1_700_007_200_000
    assert refreshed[0].time_end == _dt_from_ms(1_700_007_200_000)
    # time_start is carried forward from the first discovery, not
    # re-derived from createdTime again.
    assert refreshed[0].time_start == first[0].time_start


def test_get_file_index_device_not_found_returns_empty_list():
    client = FakeThingsBoardClient()
    provider = ThingsBoardDataProvider(client)

    assert provider.get_file_index(SOURCE_CONFIG) == []


def test_read_range_multi_key_outer_join_and_dtypes():
    client = FakeThingsBoardClient()
    _register_device(client)
    client.timeseries_response = {
        "temp": [(1_700_000_000_000, 5.5), (1_700_000_060_000, 6.0)],
        "status": [(1_700_000_000_000, "ok")],
    }
    provider = ThingsBoardDataProvider(client)
    files = [
        FileRecord(
            file_name="station_a",
            file_role="live",
            size=1,
            time_start=_dt_from_ms(1_700_000_000_000),
            time_end=_dt_from_ms(1_700_000_060_000),
            variables=["temp", "status"],
            status="active",
        )
    ]

    ds = provider.read_range(
        SOURCE_CONFIG,
        files=files,
        start=_dt_from_ms(1_700_000_000_000),
        end=_dt_from_ms(1_700_000_060_000),
    )

    assert ds.sizes["time"] == 2
    assert ds["temp"].values.dtype.kind == "f"
    assert ds["status"].values.dtype == object
    assert pd.isna(ds["status"].values[1])  # outer-joined gap, no status at the 2nd timestamp


def test_read_range_explicit_start_end_reach_client_verbatim():
    client = FakeThingsBoardClient()
    _register_device(client)
    client.timeseries_response = {"temp": [(1000, 5.5)]}
    provider = ThingsBoardDataProvider(client)
    files = [
        FileRecord(
            file_name="station_a", file_role="live", size=1,
            time_start=_dt_from_ms(0), time_end=_dt_from_ms(2000),
            variables=["temp"], status="active",
        )
    ]

    provider.read_range(
        SOURCE_CONFIG, files=files, start=_dt_from_ms(500), end=_dt_from_ms(1500), variables=["temp"]
    )

    call = client.timeseries_calls[0]
    assert call["start_ms"] == 500
    assert call["end_ms"] == 1500
    assert call["keys"] == ["temp"]


def test_read_range_none_start_end_falls_back_to_file_record_range():
    client = FakeThingsBoardClient()
    _register_device(client)
    client.timeseries_response = {"temp": [(1000, 5.5)]}
    provider = ThingsBoardDataProvider(client)
    files = [
        FileRecord(
            file_name="station_a", file_role="live", size=1,
            time_start=_dt_from_ms(100), time_end=_dt_from_ms(2000),
            variables=["temp"], status="active",
        )
    ]

    provider.read_range(SOURCE_CONFIG, files=files, start=None, end=None, variables=["temp"])

    call = client.timeseries_calls[0]
    assert call["start_ms"] == 100
    assert call["end_ms"] == 2000


def test_read_range_variables_none_uses_latest_telemetry_keys():
    client = FakeThingsBoardClient()
    _register_device(client)
    client.latest["dev-1"] = {"temp": (1000, 5.5), "humidity": (1000, 60.0)}
    client.timeseries_response = {"temp": [(1000, 5.5)], "humidity": [(1000, 60.0)]}
    provider = ThingsBoardDataProvider(client)
    files = [
        FileRecord(
            file_name="station_a", file_role="live", size=1,
            time_start=_dt_from_ms(0), time_end=_dt_from_ms(2000),
            variables=["temp", "humidity"], status="active",
        )
    ]

    provider.read_range(SOURCE_CONFIG, files=files, start=None, end=None, variables=None)

    call = client.timeseries_calls[0]
    assert call["keys"] == ["humidity", "temp"]


def test_read_range_empty_files_returns_empty_dataset():
    client = FakeThingsBoardClient()
    provider = ThingsBoardDataProvider(client)

    ds = provider.read_range(SOURCE_CONFIG, files=[], start=None, end=None)

    assert ds.sizes.get("time", 0) == 0
    assert len(client.timeseries_calls) == 0


def test_read_range_file_with_no_time_end_returns_empty_dataset():
    client = FakeThingsBoardClient()
    provider = ThingsBoardDataProvider(client)
    files = [
        FileRecord(
            file_name="station_a", file_role="live", size=0,
            time_start=None, time_end=None, variables=[], status="active",
        )
    ]

    ds = provider.read_range(SOURCE_CONFIG, files=files, start=None, end=None)

    assert ds.sizes.get("time", 0) == 0
