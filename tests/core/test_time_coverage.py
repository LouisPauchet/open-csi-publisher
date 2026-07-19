from __future__ import annotations

from datetime import datetime

from open_csi_publisher.core.builder import resolve_time_coverage
from open_csi_publisher.core.models import FileRecord


def _record(time_start, time_end, status="closed") -> FileRecord:
    return FileRecord(
        file_name="x.dat",
        file_role="archived",
        size=1,
        time_start=time_start,
        time_end=time_end,
        variables=[],
        status=status,
    )


def test_resolve_time_coverage_empty_list_returns_none():
    assert resolve_time_coverage([]) is None


def test_resolve_time_coverage_all_none_returns_none():
    # e.g. a brand-new, still-empty live file
    assert resolve_time_coverage([_record(None, None, status="active")]) is None


def test_resolve_time_coverage_single_entry():
    start = datetime(2020, 1, 1)
    end = datetime(2020, 1, 31)
    assert resolve_time_coverage([_record(start, end)]) == (start, end)


def test_resolve_time_coverage_spans_min_start_and_max_end_across_entries():
    archived = _record(datetime(2020, 1, 1), datetime(2020, 6, 30))
    live = _record(datetime(2020, 7, 1), datetime(2020, 8, 15), status="active")
    assert resolve_time_coverage([archived, live]) == (
        datetime(2020, 1, 1),
        datetime(2020, 8, 15),
    )


def test_resolve_time_coverage_ignores_entries_with_no_data_yet():
    real = _record(datetime(2020, 1, 1), datetime(2020, 1, 31))
    empty = _record(None, None, status="active")
    assert resolve_time_coverage([real, empty]) == (datetime(2020, 1, 1), datetime(2020, 1, 31))
