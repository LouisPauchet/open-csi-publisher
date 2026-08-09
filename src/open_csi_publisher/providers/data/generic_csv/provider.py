from __future__ import annotations

import pickle
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Sequence

import pandas as pd
import xarray as xr

from open_csi_publisher.core.config_schema import GenericCsvSourceConfig
from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.providers.base import DataProvider, empty_dataset
from open_csi_publisher.settings import settings
from open_csi_publisher.state.cache import NullParseCache, ParseCache


class GenericCsvDataProvider(DataProvider):
    """A second, minimal source type purpose-built to stress-test the
    DataProvider plugin boundary (implementation_plan.md §13): a single,
    exact CSV file per dataset — no live/archived fileset split, no header
    quirks. Deliberately uses a different "has this changed since last
    check" signal than LoggerNetDataProvider's file-size comparison: file
    mtime. `FileRecord.size` is reused to carry that mtime token — from the
    DataProvider ABC's perspective it's just "whatever numeric value this
    provider compares across refreshes to detect a change," not necessarily
    a byte count (matching the architecture doc's own suggested example: "a
    DB-backed source might use a last_modified column instead").
    """

    def __init__(self, data_root: Path, cache: ParseCache | NullParseCache | None = None):
        self._data_root = Path(data_root)
        self._cache = cache if cache is not None else NullParseCache()

    def get_file_index(
        self, source_config: GenericCsvSourceConfig, previous: Sequence[FileRecord] = ()
    ) -> list[FileRecord]:
        path = self._data_root / source_config.file_path
        mtime_token = path.stat().st_mtime_ns
        prev = next((p for p in previous if p.file_name == source_config.file_path), None)

        if prev is not None and prev.size == mtime_token:
            if prev.status == "active":
                return [replace(prev, status="closed")]
            return [prev]  # already closed, mtime confirmed unchanged

        parsed = self._parse_cached(path, mtime_token, source_config)
        return [
            FileRecord(
                file_name=source_config.file_path,
                file_role="live",
                size=mtime_token,
                time_start=parsed.index.min().to_pydatetime() if len(parsed) else None,
                time_end=parsed.index.max().to_pydatetime() if len(parsed) else None,
                variables=list(parsed.columns),
                status="active",
            )
        ]

    def read_range(
        self,
        source_config: GenericCsvSourceConfig,
        files: Sequence[FileRecord],
        start: datetime | None,
        end: datetime | None,
        variables: list[str] | None = None,
    ) -> xr.Dataset:
        if not files:
            return empty_dataset()

        record = files[0]
        path = self._data_root / record.file_name
        df = self._parse_cached(path, record.size, source_config, variables=variables)
        ds = xr.Dataset.from_dataframe(df)
        return ds.sel(time=slice(start, end))

    def _parse_cached(
        self,
        path: Path,
        mtime_token: int,
        source_config: GenericCsvSourceConfig,
        variables: list[str] | None = None,
    ) -> pd.DataFrame:
        """Caches the parsed file keyed on (file_path, mtime_token) so
        get_file_index()'s own parse (when mtime changed) and the read_range()
        call that immediately follows it share one parse instead of two, and so
        a later request for a different variable subset of the same file/mtime
        is a cache hit rather than a fresh parse.

        With no real cache backing this (cache_enabled=False, or no Redis
        configured at all), falls back to exactly today's behavior: a single
        parse per call, with `variables` pushed down to pandas as `usecols`
        rather than read in full and subset afterward.
        """
        if not source_config.cache_enabled or not self._cache.enabled:
            usecols = [source_config.timestamp_column, *variables] if variables is not None else None
            return self._parse(path, source_config, usecols=usecols)

        cache_key = f"genericcsv:{source_config.file_path}:{mtime_token}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            df = pickle.loads(cached)
        else:
            df = self._parse(path, source_config)
            self._cache.set(cache_key, pickle.dumps(df), ttl=settings.redis_cache_ttl_seconds)

        if variables is not None:
            df = df[[v for v in variables if v in df.columns]]
        return df

    def _parse(
        self,
        path: Path,
        source_config: GenericCsvSourceConfig,
        usecols: list[str] | None = None,
    ) -> pd.DataFrame:
        df = pd.read_csv(path, usecols=usecols)
        df[source_config.timestamp_column] = pd.to_datetime(df[source_config.timestamp_column])
        df = df.set_index(source_config.timestamp_column).rename_axis("time").sort_index()
        return df
