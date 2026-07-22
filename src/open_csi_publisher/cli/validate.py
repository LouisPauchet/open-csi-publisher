from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from open_csi_publisher.core.config_schema import DatasetConfig, LoggerNetSourceConfig
from open_csi_publisher.providers.data.loggernet.provider import (
    _backup_pattern,
    _historical_pattern,
)
from open_csi_publisher.providers.data.loggernet.toa5 import Toa5FormatError, parse_toa5_header

_NON_LOGGERNET_SOURCE_TYPES = {"generic_csv", "thingsboard"}


@dataclass
class ConfigValidationResult:
    path: Path
    status: Literal["valid", "invalid", "skipped"]
    messages: list[str] = field(default_factory=list)


def validate_loggernet_configs(
    config_dir: Path, data_root: Path | None = None
) -> list[ConfigValidationResult]:
    """Validate every `*.json` config in `config_dir` as a loggernet dataset config.

    Configs whose `source_type` is recognized but not `loggernet` are reported as
    skipped, not invalid. When `data_root` is given, each valid config's matched
    files are also checked for an actual TOA5 header — every non-TOA5 match is
    reported (unlike `LoggerNetDataProvider.matched_files`, which silently skips
    them in production), since the point of this command is maximally explicit
    diagnostics.
    """
    return [_validate_one(path, data_root) for path in sorted(Path(config_dir).glob("*.json"))]


def _validate_one(path: Path, data_root: Path | None) -> ConfigValidationResult:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ConfigValidationResult(path, "invalid", [f"invalid JSON: {exc}"])

    source_type = raw.get("source_type") if isinstance(raw, dict) else None
    if source_type in _NON_LOGGERNET_SOURCE_TYPES:
        return ConfigValidationResult(
            path, "skipped", [f"source_type={source_type!r}, not a loggernet dataset"]
        )

    try:
        config = DatasetConfig.model_validate(raw)
    except ValidationError as exc:
        return ConfigValidationResult(path, "invalid", [str(exc)])

    if data_root is None:
        return ConfigValidationResult(path, "valid")

    assert isinstance(config.source_config, LoggerNetSourceConfig)
    problems = _check_data_root(config.source_config, data_root)
    if problems:
        return ConfigValidationResult(path, "invalid", problems)
    return ConfigValidationResult(path, "valid")


def _check_data_root(source_config: LoggerNetSourceConfig, data_root: Path) -> list[str]:
    patterns = [
        source_config.file_pattern,
        _historical_pattern(source_config.file_pattern, source_config.historical_suffix),
        _backup_pattern(source_config.file_pattern),
    ]
    matched: set[Path] = set()
    for pattern in patterns:
        matched.update(Path(data_root).glob(pattern))

    problems: list[str] = []
    for candidate in sorted(matched):
        try:
            parse_toa5_header(candidate)
        except Toa5FormatError as exc:
            problems.append(str(exc))
    return problems
