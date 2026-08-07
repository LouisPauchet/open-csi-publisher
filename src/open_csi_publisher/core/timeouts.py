from __future__ import annotations

import concurrent.futures
from typing import Callable, ParamSpec, TypeVar

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="dataset-build"
)

P = ParamSpec("P")
T = TypeVar("T")


class DatasetBuildTimeoutError(TimeoutError):
    """Raised when a provider call exceeds its allotted time budget."""


def run_with_timeout(
    fn: Callable[P, T], /, *args: P.args, timeout: float, description: str, **kwargs: P.kwargs
) -> T:
    """Runs `fn` in a bounded background thread pool and enforces `timeout`.

    Python has no way to forcibly cancel a blocked syscall in another thread
    (e.g. a stalled network-mounted file read) — on timeout, the submitted
    call keeps running in its worker thread until it eventually completes or
    errors on its own. The fixed-size executor bounds the damage (later
    requests queue behind stuck threads rather than growing the thread count
    unboundedly) but doesn't reclaim the thread immediately.
    """
    future = _EXECUTOR.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise DatasetBuildTimeoutError(f"{description} exceeded {timeout}s") from None
