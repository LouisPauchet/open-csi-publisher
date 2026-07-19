from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

import yaml

from open_csi_publisher.core.config_schema import VariableSpec

_KNOWN_VARIABLES_PATH = Path(__file__).resolve().parent / "known_variables.yaml"

_GPS_PATTERNS = {
    "latitude": {"latitude", "lat"},
    "longitude": {"longitude", "lon", "long"},
}

# A shared prefix/suffix with an embedded numeric level token, e.g.
# "AirTC_2m_Avg" -> prefix="AirTC", value=2, unit="m", suffix="Avg". No real
# sample station has this pattern (synthetic test coverage only), but the
# architecture doc's own §4.2 example uses exactly this shape.
_LEVEL_PATTERN = re.compile(r"^(?P<prefix>.+?)_(?P<value>\d+)(?P<unit>[a-zA-Z]+)_(?P<suffix>.+)$")


def load_known_variables(path: Path | None = None) -> dict[str, dict[str, str]]:
    return yaml.safe_load((path or _KNOWN_VARIABLES_PATH).read_text(encoding="utf-8"))


def suggest_standard_name(
    raw_column: str, known_variables: dict[str, dict[str, str]]
) -> dict[str, str] | None:
    if raw_column in known_variables:
        return known_variables[raw_column]
    matches = difflib.get_close_matches(raw_column, known_variables.keys(), n=1, cutoff=0.8)
    return known_variables[matches[0]] if matches else None


def detect_gps_columns(raw_columns: list[str]) -> dict[str, str]:
    detected = {}
    for col in raw_columns:
        lowered = col.lower()
        for standard_name, patterns in _GPS_PATTERNS.items():
            if lowered in patterns:
                detected[col] = standard_name
                break
    return detected


def detect_extra_dimension_groups(raw_columns: list[str]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[tuple[str, int]]] = {}
    for col in raw_columns:
        match = _LEVEL_PATTERN.match(col)
        if not match:
            continue
        key = (match.group("prefix"), match.group("unit"), match.group("suffix"))
        groups.setdefault(key, []).append((col, int(match.group("value"))))

    result = []
    for (_prefix, unit, _suffix), members in groups.items():
        if len(members) < 2:
            continue  # a lone leveled column isn't a group worth combining
        ordered = sorted(members, key=lambda item: item[1])
        result.append(
            {
                "dimension_units": unit,
                "members": [
                    {"raw_name": name, "dimension_value": value} for name, value in ordered
                ],
            }
        )
    return result


def detect_old_name_matches(
    new_columns: list[str], existing_variables: list[VariableSpec]
) -> dict[str, str]:
    """Classify newly-scanned columns against an existing config's variables,
    for re-running the CLI on a dataset that already has a config: each
    result is "already_mapped" (matches a raw_name or old_names entry
    verbatim), "likely_rename" (fuzzy-matches one, probably a sensor-swap
    rename), or "new" (genuinely unrecognized)."""
    known_raw_names = {spec.raw_name for spec in existing_variables if spec.raw_name}
    known_old_names = {name for spec in existing_variables for name in spec.old_names}
    known = known_raw_names | known_old_names

    result = {}
    for col in new_columns:
        if col in known:
            result[col] = "already_mapped"
        elif difflib.get_close_matches(col, known, n=1, cutoff=0.6):
            result[col] = "likely_rename"
        else:
            result[col] = "new"
    return result
