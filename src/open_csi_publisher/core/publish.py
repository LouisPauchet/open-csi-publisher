from __future__ import annotations

from datetime import datetime


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """[start, end) of a calendar month."""
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def is_month_settled(
    year: int, month: int, *, coverage: tuple[datetime, datetime] | None, now: datetime
) -> bool:
    """A month is "settled" (safe to publish, implementation_plan.md §11) once
    data has actually been observed to continue past its end — not merely
    because wall-clock time has passed it. `min(data_end, now)` means a
    station reporting bogus future timestamps can't fast-forward completeness
    ahead of the real clock. Requires `coverage` to come from a freshly
    refreshed file index (refresh_and_get_index), so it reflects the live
    file's current state rather than stale cached info.

    A month the dataset's data doesn't even reach yet (data_start is after
    the month's end) is never settled — otherwise a station that started in
    July would vacuously "settle" every prior month it has no data for at
    all, since there'd be nothing left to append to a month that never had
    any data in the first place.
    """
    if coverage is None:
        return False
    data_start, data_end = coverage
    _, month_end = month_bounds(year, month)
    if data_start >= month_end:
        return False
    return min(data_end, now) >= month_end


def latest_settled_month(
    coverage: tuple[datetime, datetime] | None, *, now: datetime
) -> str | None:
    """The most recent "yyyy-mm" month that is settled, or None if no month
    is settled yet (e.g. the dataset's data hasn't left its first month)."""
    if coverage is None:
        return None
    _, data_end = coverage
    boundary = min(data_end, now)
    year, month = _previous_month(boundary.year, boundary.month)
    if not is_month_settled(year, month, coverage=coverage, now=now):
        return None
    return f"{year:04d}-{month:02d}"


def render_file_naming(template: str, *, station: str, table: str, year: int, month: int) -> str:
    return template.format(station=station, table=table, yyyy=f"{year:04d}", mm=f"{month:02d}")


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)
