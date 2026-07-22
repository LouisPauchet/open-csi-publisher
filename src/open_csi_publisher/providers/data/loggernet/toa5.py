from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
_NA_VALUES = ["NAN"]
_MARKER = "TOA5"
_INFO_ROW_FIELD_COUNT = 8


class Toa5FormatError(ValueError):
    """Raised when a file's header doesn't have the shape of a TOA5 file — either
    the info row doesn't unpack into the expected 8 fields, or its first field
    isn't the literal `TOA5` marker. Lets callers (the provider's file matching,
    the CLI's config validator) distinguish "this file isn't TOA5 at all" from
    other parse failures, regardless of the file's extension."""


@dataclass(frozen=True)
class Toa5Header:
    """The 4-line TOA5 header. `station_name` is provenance-only: it can differ
    between a live file and its own archived twin, so it must never be used for
    dataset identity."""

    station_name: str
    logger_model: str
    serial_no: str
    os_version: str
    program_name: str
    program_sig: str
    table_name: str
    column_names: list[str]
    units: list[str]
    agg_types: list[str]


@dataclass
class ParsedToa5File:
    path: Path
    header: Toa5Header
    dataset: xr.Dataset
    n_rows: int
    time_start: datetime | None
    time_end: datetime | None


def parse_toa5_header(path: Path) -> Toa5Header:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        info_row = next(reader)
        column_names = next(reader)
        units = next(reader)
        agg_types = next(reader)

    if len(info_row) != _INFO_ROW_FIELD_COUNT:
        raise Toa5FormatError(
            f"{path}: expected {_INFO_ROW_FIELD_COUNT} fields in the TOA5 info row, "
            f"found {len(info_row)}"
        )

    (
        marker,
        station_name,
        logger_model,
        serial_no,
        os_version,
        program_name,
        program_sig,
        table_name,
    ) = info_row

    if marker != _MARKER:
        raise Toa5FormatError(f"{path}: expected {_MARKER!r} marker, found {marker!r}")

    return Toa5Header(
        station_name=station_name,
        logger_model=logger_model,
        serial_no=serial_no,
        os_version=os_version,
        program_name=program_name,
        program_sig=program_sig,
        table_name=table_name,
        column_names=column_names,
        units=units,
        agg_types=agg_types,
    )


def parse_toa5_file(
    path: Path,
    *,
    timestamp_column: str = "TIMESTAMP",
    usecols: list[str] | None = None,
) -> ParsedToa5File:
    """Full-parse a TOA5 `.dat` file into an xr.Dataset indexed by `time`.

    Simple whole-file parse for now (pandas.read_csv from row 0) — this is where a
    future sparse timestamp->byte-offset seek index would plug in to avoid re-parsing
    large files in full on every call.
    """
    header = parse_toa5_header(path)

    read_cols: list[str] | None = None
    if usecols is not None:
        # A requested raw column may not exist in THIS file: the same dataset's
        # fileset can have column drift between its live and archived files (e.g.
        # a column added after a config/logger-program change). pandas.read_csv
        # raises if usecols references a column absent from this file's own
        # header, so intersect first — the column then simply isn't in this
        # file's parsed dataset, which reconcile_fileset's outer join already
        # turns into NaN for that file's time range, exactly as intended.
        available = set(header.column_names)
        read_cols = [
            timestamp_column,
            *(c for c in usecols if c != timestamp_column and c in available),
        ]

    try:
        df = pd.read_csv(
            path,
            skiprows=4,
            header=None,
            names=header.column_names,
            quotechar='"',
            na_values=_NA_VALUES,
            keep_default_na=True,
            usecols=read_cols,
            encoding="utf-8",
            # LoggerNet dataloggers can leave raw storage-corruption bytes (observed:
            # runs of 0xFF, likely unwritten flash) inside an otherwise well-formed
            # quoted field after a power loss. Replacing undecodable bytes instead of
            # raising keeps the rest of the file parseable; the affected field just
            # comes through as garbled text rather than its real value.
            encoding_errors="replace",
        )
    except pd.errors.EmptyDataError:
        df = pd.DataFrame(columns=read_cols or header.column_names)

    if df.shape[0] == 0:
        # pandas can drop the configured column names entirely when there is no data
        # left after skiprows; normalize so callers can always rely on them.
        df = pd.DataFrame(columns=read_cols or header.column_names)
        parsed_time = pd.to_datetime(pd.Series([], dtype="object"))
    else:
        try:
            parsed_time = pd.to_datetime(df[timestamp_column], format=_TIMESTAMP_FORMAT)
        except ValueError:
            logger.warning(
                "timestamps in %s did not match %s, falling back to flexible parsing",
                path,
                _TIMESTAMP_FORMAT,
            )
            parsed_time = pd.to_datetime(df[timestamp_column])

    df = df.drop(columns=[timestamp_column])
    df.index = pd.DatetimeIndex(parsed_time, name="time")

    dataset = xr.Dataset.from_dataframe(df)
    dataset.attrs.update(
        station_name=header.station_name,
        logger_model=header.logger_model,
        serial_no=header.serial_no,
        os_version=header.os_version,
        program_name=header.program_name,
        program_sig=header.program_sig,
        table_name=header.table_name,
        source_file=str(path),
    )
    for name, unit, agg_type in zip(header.column_names, header.units, header.agg_types):
        if name in dataset.data_vars:
            dataset[name].attrs["loggernet_units"] = unit
            dataset[name].attrs["loggernet_agg_type"] = agg_type

    n_rows = df.shape[0]
    time_start = parsed_time.min().to_pydatetime() if n_rows else None
    time_end = parsed_time.max().to_pydatetime() if n_rows else None

    return ParsedToa5File(
        path=path,
        header=header,
        dataset=dataset,
        n_rows=n_rows,
        time_start=time_start,
        time_end=time_end,
    )
