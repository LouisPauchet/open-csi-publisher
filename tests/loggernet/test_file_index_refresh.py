from __future__ import annotations

from datetime import datetime
from typing import Sequence

from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.index.service import refresh_and_get_index
from open_csi_publisher.providers.base import DataProvider

ARCHIVED = FileRecord(
    file_name="station_a/Table_Historical.dat",
    file_role="archived",
    size=1000,
    time_start=datetime(2020, 1, 1),
    time_end=datetime(2025, 12, 31),
    variables=["AirT_C"],
    status="closed",
)
LIVE_V1 = FileRecord(
    file_name="station_a/Table.dat",
    file_role="live",
    size=50,
    time_start=datetime(2026, 1, 1),
    time_end=datetime(2026, 1, 2),
    variables=["AirT_C"],
    status="active",
)
LIVE_V2 = FileRecord(
    file_name="station_a/Table.dat",
    file_role="live",
    size=90,
    time_start=datetime(2026, 1, 1),
    time_end=datetime(2026, 1, 5),
    variables=["AirT_C"],
    status="active",
)


class FakeDataProvider(DataProvider):
    """Records what `previous` it was called with each time, and returns a
    pre-scripted sequence of results — enough to test the refresh orchestration
    without needing real files; the LoggerNet-specific state machine itself is
    already covered against real data in test_provider.py."""

    def __init__(self, responses: list[list[FileRecord]]):
        self._responses = list(responses)
        self.calls: list[Sequence[FileRecord]] = []

    def get_file_index(self, source_config, previous: Sequence[FileRecord] = ()) -> list[FileRecord]:
        self.calls.append(previous)
        return self._responses.pop(0)

    def read_range(self, source_config, files, start, end, variables=None):
        raise NotImplementedError


def test_first_refresh_calls_provider_with_no_previous_state(db_session):
    provider = FakeDataProvider([[ARCHIVED, LIVE_V1]])
    result = refresh_and_get_index(db_session, "station_a", source_config=None, data_provider=provider)

    assert result == [ARCHIVED, LIVE_V1]
    assert provider.calls[0] == []


def test_second_refresh_passes_persisted_state_as_previous(db_session):
    provider = FakeDataProvider([[ARCHIVED, LIVE_V1], [ARCHIVED, LIVE_V2]])
    refresh_and_get_index(db_session, "station_a", source_config=None, data_provider=provider)
    result = refresh_and_get_index(db_session, "station_a", source_config=None, data_provider=provider)

    assert result == [ARCHIVED, LIVE_V2]
    passed_previous = {r.file_name: r for r in provider.calls[1]}
    assert passed_previous["station_a/Table.dat"] == LIVE_V1
    assert passed_previous["station_a/Table_Historical.dat"] == ARCHIVED


def test_refresh_is_isolated_per_dataset(db_session):
    provider_a = FakeDataProvider([[LIVE_V1]])
    provider_b = FakeDataProvider([[ARCHIVED]])

    refresh_and_get_index(db_session, "station_a", source_config=None, data_provider=provider_a)
    refresh_and_get_index(db_session, "station_b", source_config=None, data_provider=provider_b)

    assert provider_a.calls[0] == []
    assert provider_b.calls[0] == []  # station_b's refresh must not see station_a's files
