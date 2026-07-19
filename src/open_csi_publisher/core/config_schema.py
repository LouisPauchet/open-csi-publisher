from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class ExtraDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    units: str


class VariableMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_name: str
    dimension_value: float | int | str


class VariableSpec(BaseModel):
    """One config `variables[]` entry: either a single raw column, or a group of raw
    columns stacked along an `extra_dimension` (mutually exclusive)."""

    model_config = ConfigDict(extra="forbid")

    raw_name: str | None = None
    old_names: list[str] = []
    standard_name: str | None = None
    units: str | None = None
    dtype: Literal["numeric", "string"] = "numeric"
    extra_dimension: ExtraDimension | None = None
    members: list[VariableMember] = []

    @model_validator(mode="after")
    def _check_shape(self) -> "VariableSpec":
        if self.extra_dimension is not None:
            if self.raw_name is not None:
                raise ValueError("a variable cannot set both raw_name and extra_dimension")
            if not self.members:
                raise ValueError("extra_dimension variables require at least one member")
            if self.standard_name is None:
                raise ValueError(
                    "extra_dimension variables require standard_name (there is no "
                    "single raw_name to fall back on as the canonical identity)"
                )
        elif self.raw_name is None:
            raise ValueError("a variable must set either raw_name or extra_dimension+members")
        return self

    @property
    def canonical_name(self) -> str:
        return self.standard_name or self.raw_name  # type: ignore[return-value]

    def all_raw_names(self) -> list[str]:
        """Every raw column name this spec maps, including old_names and members."""
        if self.extra_dimension is not None:
            return [m.raw_name for m in self.members]
        assert self.raw_name is not None
        return [self.raw_name, *self.old_names]


class Deployment(BaseModel):
    """A time window for either a `fixed` station's position or a `mobile` platform's
    identity — which fields are required/forbidden depends on the dataset's
    platform_type, enforced by DatasetConfig, not here."""

    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime | None = None

    # fixed-platform fields
    lat: float | None = None
    lon: float | None = None
    elevation: float | None = None

    # mobile-platform fields
    platform_name: str | None = None
    instrument_config: str | None = None
    notes: str | None = None


class LoggerNetSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_pattern: str
    timestamp_column: str = "TIMESTAMP"
    table_name: str | None = None
    historical_suffix: str = "_Historical"
    record_column: str = "RECORD"


class MetadataSpec(BaseModel):
    """CF-ish global attributes. Extra keys (e.g. department, project) are preserved
    verbatim and are what the listing page's open-ended metadata filter searches over."""

    model_config = ConfigDict(extra="allow")

    title: str
    institution: str | None = None
    license: str | None = None
    naming_authority: str | None = None
    standard_name_vocabulary: str = "CF-1.10"


class OutputSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_naming: str
    publish: bool = False


class DatasetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_type: Literal["loggernet"]
    access: Literal["public", "restricted"]
    source_config: LoggerNetSourceConfig
    variables: list[VariableSpec]
    platform_type: Literal["fixed", "mobile"]
    deployments: list[Deployment]
    metadata: MetadataSpec
    output: OutputSpec

    @model_validator(mode="after")
    def _check_deployments(self) -> "DatasetConfig":
        deployments = self.deployments
        if not deployments:
            raise ValueError("at least one deployment is required")

        for i, dep in enumerate(deployments):
            if dep.end is not None and dep.end <= dep.start:
                raise ValueError(f"deployments[{i}]: end must be after start")
            is_last = i == len(deployments) - 1
            if dep.end is None and not is_last:
                raise ValueError("only the last deployment may be open-ended (end: null)")
            if not is_last:
                nxt = deployments[i + 1]
                if dep.start > nxt.start:
                    raise ValueError("deployments must be sorted by start ascending")
                if dep.end is not None and dep.end > nxt.start:
                    raise ValueError(f"deployments[{i}] and deployments[{i + 1}] overlap")

        if self.platform_type == "fixed":
            for i, dep in enumerate(deployments):
                if dep.lat is None or dep.lon is None:
                    raise ValueError(f"deployments[{i}]: fixed platform requires lat and lon")
                if dep.platform_name is not None or dep.instrument_config is not None:
                    raise ValueError(
                        f"deployments[{i}]: platform_name/instrument_config are mobile-only fields"
                    )
        else:  # mobile
            for i, dep in enumerate(deployments):
                if dep.platform_name is None:
                    raise ValueError(f"deployments[{i}]: mobile platform requires platform_name")
                if dep.lat is not None or dep.lon is not None or dep.elevation is not None:
                    raise ValueError(f"deployments[{i}]: lat/lon/elevation are fixed-only fields")
            standard_names = {v.standard_name for v in self.variables if v.standard_name}
            missing = {"latitude", "longitude"} - standard_names
            if missing:
                raise ValueError(
                    "mobile datasets must map variables with standard_name "
                    f"{sorted(missing)} (position comes from the data, not deployments)"
                )
        return self

    @model_validator(mode="after")
    def _check_no_raw_name_collisions(self) -> "DatasetConfig":
        seen: dict[str, int] = {}
        for i, var in enumerate(self.variables):
            for raw_name in var.all_raw_names():
                if raw_name in seen:
                    raise ValueError(
                        f"raw column '{raw_name}' is mapped by both variables[{seen[raw_name]}] "
                        f"and variables[{i}] (via raw_name/old_names/members)"
                    )
                seen[raw_name] = i
        return self
