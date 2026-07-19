from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Sequence

import xarray as xr

from open_csi_publisher.core.config_schema import LoggerNetSourceConfig
from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.providers.base import DataProvider
from open_csi_publisher.providers.data.loggernet.fileset import classify_files, reconcile_fileset
from open_csi_publisher.providers.data.loggernet.toa5 import parse_toa5_file


class LoggerNetDataProvider(DataProvider):
    def __init__(self, data_root: Path):
        self._data_root = Path(data_root)

    def get_file_index(
        self, source_config: LoggerNetSourceConfig, previous: Sequence[FileRecord] = ()
    ) -> list[FileRecord]:
        matched = self._matched_files(source_config)
        classified = classify_files(matched, historical_suffix=source_config.historical_suffix)
        previous_by_name = {r.file_name: r for r in previous}

        records: list[FileRecord] = []
        for c in classified:
            rel_name = c.path.relative_to(self._data_root).as_posix()
            prev = previous_by_name.get(rel_name)

            if c.role == "archived":
                if prev is not None and prev.status == "closed":
                    records.append(prev)  # closed archived files are never reparsed
                else:
                    records.append(self._parse_record(c.path, rel_name, "archived", "closed", source_config))
                continue

            # live: at most one, per classify_files
            current_size = c.path.stat().st_size
            if prev is None or prev.size != current_size:
                records.append(self._parse_record(c.path, rel_name, "live", "active", source_config))
            elif prev.status == "active":
                records.append(replace(prev, status="closed"))  # unchanged since last check
            else:
                records.append(prev)  # already closed, belt-and-suspenders re-stat confirmed no change

        return records

    def read_range(
        self,
        source_config: LoggerNetSourceConfig,
        files: Sequence[FileRecord],
        start: datetime | None,
        end: datetime | None,
        variables: list[str] | None = None,
    ) -> xr.Dataset:
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

    def _matched_files(self, source_config: LoggerNetSourceConfig) -> list[Path]:
        patterns = [
            source_config.file_pattern,
            _historical_pattern(source_config.file_pattern, source_config.historical_suffix),
            _backup_pattern(source_config.file_pattern),
        ]
        matched: set[Path] = set()
        for pattern in patterns:
            matched.update(self._data_root.glob(pattern))
        return sorted(matched)

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
    ):
        return parse_toa5_file(
            self._data_root / record.file_name,
            timestamp_column=source_config.timestamp_column,
            usecols=variables,
        )


def _historical_pattern(file_pattern: str, historical_suffix: str) -> str:
    return file_pattern[: -len(".dat")] + historical_suffix + ".dat"


def _backup_pattern(file_pattern: str) -> str:
    return file_pattern + ".backup*"
