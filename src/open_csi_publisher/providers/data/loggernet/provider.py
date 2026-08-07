from __future__ import annotations

import os
import pickle
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Sequence

import xarray as xr
from loguru import logger

from open_csi_publisher.core.config_schema import LoggerNetSourceConfig
from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.providers.base import DataProvider, empty_dataset
from open_csi_publisher.providers.data.loggernet.fileset import (
    AmbiguousFileSetError,
    ClassifiedFile,
    classify_files,
    count_live_candidates,
    reconcile_fileset,
)
from open_csi_publisher.providers.data.loggernet.toa5 import (
    ParsedToa5File,
    Toa5FormatError,
    parse_toa5_file,
    parse_toa5_header,
    parse_toa5_start_time,
)
from open_csi_publisher.settings import settings
from open_csi_publisher.state.cache import NullParseCache, ParseCache


class LoggerNetDataProvider(DataProvider):
    def __init__(self, data_root: Path, cache: ParseCache | NullParseCache | None = None):
        self._data_root = Path(data_root)
        self._cache = cache if cache is not None else NullParseCache()

    def get_file_index(
        self, source_config: LoggerNetSourceConfig, previous: Sequence[FileRecord] = ()
    ) -> list[FileRecord]:
        matched = self.matched_files(source_config)
        try:
            classified = classify_files(matched, historical_suffix=source_config.historical_suffix)
        except AmbiguousFileSetError:
            if count_live_candidates(matched, historical_suffix=source_config.historical_suffix) == 0:
                logger.warning(
                    "no live file yet for {} — treating as no data available",
                    source_config.file_pattern,
                )
                return []
            raise  # >1 live file: a genuine misconfiguration, not "no data yet"
        previous_by_name = {r.file_name: r for r in previous}
        n_parsed = 0

        # Live file: unchanged behavior — full parse only when its size
        # actually changed since the last check.
        live_classified = next(c for c in classified if c.role == "live")  # exactly one, per classify_files
        live_rel_name = live_classified.path.relative_to(self._data_root).as_posix()
        live_prev = previous_by_name.get(live_rel_name)
        current_size = live_classified.path.stat().st_size
        if live_prev is None or live_prev.size != current_size:
            live_record = self._parse_record(live_classified.path, live_rel_name, "live", "active", source_config)
            n_parsed += 1
        elif live_prev.status == "active":
            live_record = replace(live_prev, status="closed")  # unchanged since last check
        else:
            live_record = live_prev  # already closed, belt-and-suspenders re-stat confirmed no change

        archived_records, archived_n_parsed = self._archived_records(
            [c for c in classified if c.role == "archived"],
            previous_by_name,
            live_record,
            source_config,
        )
        n_parsed += archived_n_parsed
        records = archived_records + [live_record]

        logger.info(
            "file index for {}: {} files matched, {} newly parsed, {} reused from previous index",
            source_config.file_pattern,
            len(matched),
            n_parsed,
            len(matched) - n_parsed,
        )
        return records

    def _archived_records(
        self,
        archived_classified: list[ClassifiedFile],
        previous_by_name: dict[str, FileRecord],
        live_record: FileRecord,
        source_config: LoggerNetSourceConfig,
    ) -> tuple[list[FileRecord], int]:
        """Builds each archived file's FileRecord. A closed, already-known file is
        reused verbatim (never touched again). Any other archived file only has its
        first timestamp read (parse_toa5_start_time — never a full-body parse); its
        time_end is derived afterward as the next (chronologically later) file's
        time_start, or the live file's time_start for the last one — always >= the
        file's own true last timestamp, so core/builder.py's _select_files_covering()
        can only become more inclusive under this approximation, never drop real
        data. This is what makes file-index refresh cheap regardless of how many
        archived files a station has accumulated.
        """
        candidates: list[tuple[str, Path, FileRecord | None, datetime | None]] = []
        n_parsed = 0
        for c in archived_classified:
            rel_name = c.path.relative_to(self._data_root).as_posix()
            prev = previous_by_name.get(rel_name)
            if prev is not None and prev.status == "closed":
                candidates.append((rel_name, c.path, prev, prev.time_start))
                continue
            start = parse_toa5_start_time(c.path, timestamp_column=source_config.timestamp_column)
            n_parsed += 1
            candidates.append((rel_name, c.path, None, start))

        candidates.sort(key=lambda item: item[3] or datetime.min)

        records: list[FileRecord] = []
        for i, (rel_name, path, prev, start) in enumerate(candidates):
            if prev is not None:
                records.append(prev)  # already fully known, untouched
                continue
            next_start = candidates[i + 1][3] if i + 1 < len(candidates) else live_record.time_start
            header = parse_toa5_header(path)
            variables = [name for name in header.column_names if name != source_config.timestamp_column]
            records.append(
                FileRecord(
                    file_name=rel_name,
                    file_role="archived",
                    size=path.stat().st_size,
                    time_start=start,
                    time_end=next_start,
                    variables=variables,
                    status="closed",
                )
            )
        return records, n_parsed

    def read_range(
        self,
        source_config: LoggerNetSourceConfig,
        files: Sequence[FileRecord],
        start: datetime | None,
        end: datetime | None,
        variables: list[str] | None = None,
    ) -> xr.Dataset:
        if not files:
            return empty_dataset()

        archived_parsed = [
            self._parse_selected(f, source_config, variables)
            for f in files
            if f.file_role == "archived"
        ]
        live_record = next((f for f in files if f.file_role == "live"), None)
        live_parsed = (
            self._parse_selected(live_record, source_config, variables)
            if live_record is not None
            else None
        )
        combined = reconcile_fileset(archived=archived_parsed, live=live_parsed)
        return combined.sel(time=slice(start, end))

    def matched_files(self, source_config: LoggerNetSourceConfig) -> list[Path]:
        """Every file matching `source_config`'s glob patterns whose header actually
        has the shape of a TOA5 file — a file_pattern no longer implies a `.dat`
        extension, so content, not extension, is what distinguishes a real TOA5
        file from something else that happens to match the glob (e.g. a stray
        notes file dropped in the same directory)."""
        patterns = [
            source_config.file_pattern,
            _historical_pattern(source_config.file_pattern, source_config.historical_suffix),
            _backup_pattern(source_config.file_pattern),
        ]
        matched: set[Path] = set()
        for pattern in patterns:
            matched.update(self._data_root.glob(pattern))

        valid: list[Path] = []
        for path in sorted(matched):
            try:
                parse_toa5_header(path)
            except Toa5FormatError as exc:
                logger.warning("skipping {}: {}", path, exc)
                continue
            valid.append(path)
        return valid

    def _parse_record(
        self,
        path: Path,
        rel_name: str,
        role: str,
        status: str,
        source_config: LoggerNetSourceConfig,
    ) -> FileRecord:
        parsed = parse_toa5_file(path, timestamp_column=source_config.timestamp_column)
        return FileRecord(
            file_name=rel_name,
            file_role=role,  # type: ignore[arg-type]
            size=path.stat().st_size,
            time_start=parsed.time_start,
            time_end=parsed.time_end,
            variables=list(parsed.dataset.data_vars),
            status=status,  # type: ignore[arg-type]
        )

    def _parse_selected(
        self,
        record: FileRecord,
        source_config: LoggerNetSourceConfig,
        variables: list[str] | None,
    ) -> ParsedToa5File:
        if not source_config.cache_enabled or not self._cache.enabled:
            return parse_toa5_file(
                self._data_root / record.file_name,
                timestamp_column=source_config.timestamp_column,
                usecols=variables,
            )

        # Keyed on (file_name, size): a closed archived file's size never
        # changes, so its cache entry is effectively permanent (within its long
        # TTL); a live file's size changes as new rows are appended, so a new
        # entry naturally appears whenever it does.
        cache_key = f"loggernet:{record.file_name}:{record.size}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            parsed = pickle.loads(cached)
        else:
            # Always parse the whole file here (no usecols pushdown) so a
            # later request for a different variable subset of the same
            # file/size is still a cache hit, rather than a fresh miss.
            parsed = parse_toa5_file(
                self._data_root / record.file_name, timestamp_column=source_config.timestamp_column
            )
            ttl = (
                settings.redis_archived_cache_ttl_seconds
                if record.status == "closed"
                else settings.redis_cache_ttl_seconds
            )
            self._cache.set(cache_key, pickle.dumps(parsed), ttl=ttl)

        if variables is not None:
            keep = [v for v in variables if v in parsed.dataset.data_vars]
            parsed = replace(parsed, dataset=parsed.dataset[keep])
        return parsed


def _historical_pattern(file_pattern: str, historical_suffix: str) -> str:
    stem, ext = os.path.splitext(file_pattern)
    return stem + historical_suffix + ext


def _backup_pattern(file_pattern: str) -> str:
    return file_pattern + ".backup*"
