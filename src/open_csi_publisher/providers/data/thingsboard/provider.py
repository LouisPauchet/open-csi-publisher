from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Sequence

import pandas as pd
import xarray as xr

from open_csi_publisher.core.config_schema import ThingsBoardSourceConfig
from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.providers.base import DataProvider
from open_csi_publisher.providers.thingsboard_client import ThingsBoardClient


class ThingsBoardDataProvider(DataProvider):
    """One synthetic FileRecord per dataset (mirrors GenericCsvDataProvider's
    "single file, no live/archived split" pattern) representing a ThingsBoard
    device's whole telemetry stream. Unlike file-based providers, ThingsBoard's
    API supports direct arbitrary-range history queries, so read_range always
    queries the exact requested window straight from the API — the file index
    here exists to satisfy the shared DataProvider contract and report
    time-coverage, not to gate an expensive local reparse.
    """

    def __init__(self, client: ThingsBoardClient):
        self._client = client

    def get_file_index(
        self, source_config: ThingsBoardSourceConfig, previous: Sequence[FileRecord] = ()
    ) -> list[FileRecord]:
        device = self._client.get_device_by_name(source_config.device_name)
        if device is None:
            return []

        device_id = device["id"]["id"]
        latest = self._client.get_latest_telemetry(device_id)
        change_token = max((ts for ts, _ in latest.values()), default=None)

        prev = next((p for p in previous if p.file_name == source_config.device_name), None)

        if prev is not None and change_token == prev.size:
            if prev.status == "active":
                return [replace(prev, status="closed")]
            return [prev]

        return [
            FileRecord(
                file_name=source_config.device_name,
                file_role="live",
                size=change_token if change_token is not None else 0,
                time_start=(
                    prev.time_start if prev is not None else _from_epoch_ms(device["createdTime"])
                ),
                time_end=_from_epoch_ms(change_token) if change_token is not None else None,
                variables=sorted(latest),
                status="active",
            )
        ]

    def read_range(
        self,
        source_config: ThingsBoardSourceConfig,
        files: Sequence[FileRecord],
        start: datetime | None,
        end: datetime | None,
        variables: list[str] | None = None,
    ) -> xr.Dataset:
        if not files or files[0].time_end is None:
            return _empty_dataset()

        device = self._client.get_device_by_name(source_config.device_name)
        if device is None:
            return _empty_dataset()
        device_id = device["id"]["id"]

        keys = variables if variables is not None else sorted(self._client.get_latest_telemetry(device_id))

        record = files[0]
        start_ms = _to_epoch_ms(start if start is not None else record.time_start)
        end_ms = _to_epoch_ms(end if end is not None else record.time_end)

        raw = self._client.get_timeseries(device_id, keys, start_ms, end_ms)
        return _telemetry_to_dataset(raw)


def _telemetry_to_dataset(raw: dict[str, list[tuple[int, Any]]]) -> xr.Dataset:
    series = {}
    for key, points in raw.items():
        if not points:
            continue
        index = pd.to_datetime([p[0] for p in points], unit="ms", utc=True).tz_localize(None)
        series[key] = pd.Series([p[1] for p in points], index=index)

    if not series:
        return _empty_dataset()

    df = pd.DataFrame(series).rename_axis("time").sort_index()
    return xr.Dataset.from_dataframe(df)


def _empty_dataset() -> xr.Dataset:
    return xr.Dataset(coords={"time": pd.DatetimeIndex([], name="time")})


def _to_epoch_ms(value: datetime) -> int:
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _from_epoch_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(tzinfo=None)
