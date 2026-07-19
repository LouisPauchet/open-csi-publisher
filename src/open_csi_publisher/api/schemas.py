from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class DatasetSummary(BaseModel):
    id: str
    title: str
    institution: str | None
    platform_type: Literal["fixed", "mobile"]
    standard_names: list[str]
    metadata: dict[str, Any]
    position: dict[str, float | None] | None


class DatasetListResponse(BaseModel):
    datasets: list[DatasetSummary]
    total: int


class VariableDetail(BaseModel):
    name: str
    standard_name: str | None
    units: str | None
    dtype: Literal["numeric", "string"]


class DeploymentInfo(BaseModel):
    start: datetime
    end: datetime | None
    lat: float | None
    lon: float | None
    elevation: float | None
    platform_name: str | None


class TimeCoverage(BaseModel):
    start: datetime
    end: datetime


class DatasetDetail(BaseModel):
    id: str
    title: str
    metadata: dict[str, Any]
    platform_type: Literal["fixed", "mobile"]
    access: Literal["public", "restricted"]
    variables: list[VariableDetail]
    deployments: list[DeploymentInfo]
    time_coverage: TimeCoverage | None
