from __future__ import annotations

from datetime import datetime

from open_csi_publisher.core.publish import (
    is_month_settled,
    latest_settled_month,
    month_bounds,
    render_file_naming,
)


def test_month_bounds_ordinary_month():
    start, end = month_bounds(2026, 7)
    assert start == datetime(2026, 7, 1)
    assert end == datetime(2026, 8, 1)


def test_month_bounds_december_rolls_into_next_year():
    start, end = month_bounds(2026, 12)
    assert start == datetime(2026, 12, 1)
    assert end == datetime(2027, 1, 1)


def test_is_month_settled_false_when_coverage_none():
    assert is_month_settled(2026, 6, coverage=None, now=datetime(2026, 7, 19)) is False


def test_is_month_settled_true_when_data_reaches_past_month_end():
    coverage = (datetime(2020, 1, 1), datetime(2026, 7, 5))
    assert is_month_settled(2026, 6, coverage=coverage, now=datetime(2026, 7, 19)) is True


def test_is_month_settled_false_when_data_still_within_the_month():
    coverage = (datetime(2020, 1, 1), datetime(2026, 6, 15))
    assert is_month_settled(2026, 6, coverage=coverage, now=datetime(2026, 7, 19)) is False


def test_is_month_settled_false_when_now_has_not_reached_month_end_even_if_data_claims_to():
    # a station reporting bogus future timestamps must not fast-forward
    # completeness ahead of the actual wall clock
    coverage = (datetime(2020, 1, 1), datetime(2099, 1, 1))
    assert is_month_settled(2026, 6, coverage=coverage, now=datetime(2026, 6, 15)) is False


def test_is_month_settled_false_when_data_has_not_started_yet_that_month():
    # a station whose data starts in July has no June data at all — June must
    # not vacuously "settle" just because data has trivially progressed past it
    coverage = (datetime(2026, 7, 10), datetime(2026, 7, 15))
    assert is_month_settled(2026, 6, coverage=coverage, now=datetime(2026, 7, 19)) is False


def test_is_month_settled_exactly_at_month_end_boundary_is_settled():
    coverage = (datetime(2020, 1, 1), datetime(2026, 7, 1))  # exactly month_end of June
    assert is_month_settled(2026, 6, coverage=coverage, now=datetime(2026, 7, 19)) is True


def test_latest_settled_month_none_when_coverage_none():
    assert latest_settled_month(None, now=datetime(2026, 7, 19)) is None


def test_latest_settled_month_returns_previous_month_when_data_reaches_current_month():
    coverage = (datetime(2020, 1, 1), datetime(2026, 7, 19, 14, 0))
    assert latest_settled_month(coverage, now=datetime(2026, 7, 19)) == "2026-06"


def test_latest_settled_month_handles_year_rollover():
    coverage = (datetime(2020, 1, 1), datetime(2026, 1, 5))
    assert latest_settled_month(coverage, now=datetime(2026, 1, 19)) == "2025-12"


def test_latest_settled_month_none_when_data_has_not_left_its_first_month_yet():
    coverage = (datetime(2026, 7, 10), datetime(2026, 7, 15))
    assert latest_settled_month(coverage, now=datetime(2026, 7, 19)) is None


def test_render_file_naming_substitutes_placeholders():
    result = render_file_naming(
        "{station}_{table}_{yyyy}-{mm}.nc", station="kapp_thordsen_10minute",
        table="Table_10minute", year=2026, month=7,
    )
    assert result == "kapp_thordsen_10minute_Table_10minute_2026-07.nc"
