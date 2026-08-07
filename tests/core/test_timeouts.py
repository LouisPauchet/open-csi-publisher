from __future__ import annotations

import time

import pytest

from open_csi_publisher.core.timeouts import DatasetBuildTimeoutError, run_with_timeout


def test_run_with_timeout_returns_result_when_fast_enough():
    result = run_with_timeout(lambda x: x * 2, 21, timeout=1.0, description="fast call")
    assert result == 42


def test_run_with_timeout_raises_dataset_build_timeout_error_when_too_slow():
    def slow():
        time.sleep(0.5)
        return "never seen"

    with pytest.raises(DatasetBuildTimeoutError) as exc_info:
        run_with_timeout(slow, timeout=0.05, description="slow call")
    assert "slow call" in str(exc_info.value)
    assert "0.05" in str(exc_info.value)


def test_run_with_timeout_propagates_the_callables_own_exception():
    def boom():
        raise ValueError("real failure")

    with pytest.raises(ValueError, match="real failure"):
        run_with_timeout(boom, timeout=1.0, description="failing call")


def test_run_with_timeout_forwards_args_and_kwargs():
    def combine(a, b, *, c):
        return f"{a}-{b}-{c}"

    result = run_with_timeout(combine, "x", "y", timeout=1.0, description="kwargs call", c="z")
    assert result == "x-y-z"
