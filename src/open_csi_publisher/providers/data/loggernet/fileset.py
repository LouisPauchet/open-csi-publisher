from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Sequence

import xarray as xr
from loguru import logger

from open_csi_publisher.providers.data.loggernet.toa5 import ParsedToa5File


class AmbiguousFileSetError(ValueError):
    """Raised when a file_pattern doesn't resolve to exactly one live file."""


@dataclass(frozen=True)
class ClassifiedFile:
    path: Path
    role: Literal["live", "archived"]


def classify_files(
    paths: Sequence[Path], *, historical_suffix: str = "_Historical"
) -> list[ClassifiedFile]:
    """Split matched files into the single actively-appended `live` file and zero or
    more `archived` files (implementation_plan.md real-data findings): a file is
    archived if its stem ends with `historical_suffix`, or if it matches LoggerNet's
    own `.backup`/`.backup1`/... rollover convention (a fixed LoggerNet mechanism,
    not a per-site naming choice, so recognized unconditionally). Everything else is
    `live`; there must be exactly one.
    """
    classified = [
        ClassifiedFile(path, "archived" if _is_archived(path, historical_suffix) else "live")
        for path in paths
    ]
    live = [c for c in classified if c.role == "live"]
    if len(live) != 1:
        raise AmbiguousFileSetError(
            f"expected exactly one live file, found {len(live)} among {[str(p) for p in paths]}"
        )
    return classified


def _is_archived(path: Path, historical_suffix: str) -> bool:
    if path.stem.endswith(historical_suffix):
        return True
    return any(suffix.startswith(".backup") for suffix in path.suffixes)


def reconcile_fileset(
    *, archived: Sequence[ParsedToa5File], live: ParsedToa5File | None
) -> xr.Dataset:
    """Combine zero-or-more archived files with an optional live file into one
    continuous time series (implementation_plan.md real-data findings): archived
    files are ordered by their own parsed time_start (not filename), then the live
    file last if present; an outer join on variable name handles column drift
    automatically (a column present in only one file becomes NaN outside that
    file's time range); exact-timestamp collisions are resolved in favor of
    whichever file was concatenated later (the live file, when present); real gaps
    between files are left as gaps, never interpolated.

    `live` is optional because a query covering only an old time window may only
    need archived files at all (see the core builder's file selection, which skips
    the live file entirely when the requested range predates it).
    """
    ordered = sorted(archived, key=lambda p: p.time_start or datetime.min)
    if live is not None:
        ordered = [*ordered, live]
    if not ordered:
        raise ValueError("reconcile_fileset requires at least one parsed file")

    combined = xr.concat(
        [p.dataset for p in ordered],
        dim="time",
        data_vars="all",
        join="outer",
        combine_attrs="drop_conflicts",
    )

    df = combined.to_dataframe()
    deduped = df[~df.index.duplicated(keep="last")].sort_index()
    result = xr.Dataset.from_dataframe(deduped)
    result.attrs = dict(combined.attrs)
    for name, var in combined.data_vars.items():
        if name in result.data_vars:
            result[name].attrs = dict(var.attrs)

    programs = {p.header.program_name for p in ordered}
    if len(programs) > 1:
        logger.info(
            "fileset for {} spans a logger reprogram: program_name differs across "
            "contributing files ({})",
            live.path,
            sorted(programs),
        )

    return result
