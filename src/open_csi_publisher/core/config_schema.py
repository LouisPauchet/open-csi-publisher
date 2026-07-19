from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


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

    @field_validator("start", "end")
    @classmethod
    def _naive_utc(cls, v: datetime | None) -> datetime | None:
        # Raw LoggerNet timestamps carry no timezone and are treated as UTC by
        # convention (implementation_plan.md real-data findings). A deployment
        # boundary written with an explicit offset (e.g. trailing "Z") is converted
        # to UTC and then made naive, so it compares directly against the naive
        # `time` coordinate parsed from the data instead of raising a
        # naive-vs-aware TypeError.
        if v is not None and v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v


class LoggerNetSourceConfig(BaseModel):
    """`file_pattern` matches the live file ONLY and must end with the literal
    `.dat` (may glob earlier segments, e.g. `*_Min.dat`) — the provider derives the
    archived-file patterns from it (`_Historical.dat` inserted before the trailing
    `.dat`, plus a `.dat.backup*` variant), rather than requiring one glob to catch
    all three naming conventions at once. That single-glob approach doesn't work
    when one table name is a prefix of another (e.g. `Min` vs `Min10` vs `Min60`):
    a pattern like `*_Min*` would also match `*_Min10.dat`.
    """

    model_config = ConfigDict(extra="forbid")

    file_pattern: str
    timestamp_column: str = "TIMESTAMP"
    table_name: str | None = None
    historical_suffix: str = "_Historical"
    record_column: str = "RECORD"

    @model_validator(mode="after")
    def _check_file_pattern(self) -> "LoggerNetSourceConfig":
        if not self.file_pattern.endswith(".dat"):
            raise ValueError("file_pattern must end with '.dat' (the live file's extension)")
        return self


class GenericCsvSourceConfig(BaseModel):
    """A minimal second source type, purpose-built to stress-test the
    ConfigProvider/DataProvider plugin boundary (implementation_plan.md §13) —
    a single, exact CSV file per dataset, no live/archived fileset split."""

    model_config = ConfigDict(extra="forbid")

    file_path: str
    timestamp_column: str = "timestamp"


_SOURCE_CONFIG_TYPES: dict[str, type[BaseModel]] = {
    "loggernet": LoggerNetSourceConfig,
    "generic_csv": GenericCsvSourceConfig,
}


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
    source_type: Literal["loggernet", "generic_csv"]
    access: Literal["public", "restricted"]
    source_config: LoggerNetSourceConfig | GenericCsvSourceConfig
    variables: list[VariableSpec]
    platform_type: Literal["fixed", "mobile"]
    deployments: list[Deployment]
    metadata: MetadataSpec
    output: OutputSpec

    @model_validator(mode="before")
    @classmethod
    def _resolve_source_config_type(cls, data: Any) -> Any:
        """`source_config`'s shape depends on the sibling `source_type` field.
        Pydantic's discriminated-union support needs the discriminator field
        embedded IN each union member, not a sibling on the parent — so this
        picks and validates the right sub-model explicitly, before Pydantic's
        own field-level union matching runs. Keeps the JSON shape unchanged
        (source_type stays a top-level sibling of source_config, as every
        existing config already has it) rather than nesting the discriminator
        inside source_config.
        """
        if isinstance(data, dict) and isinstance(data.get("source_config"), dict):
            model_cls = _SOURCE_CONFIG_TYPES.get(data.get("source_type"))
            if model_cls is not None:
                data = dict(data)
                data["source_config"] = model_cls.model_validate(data["source_config"])
        return data

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
