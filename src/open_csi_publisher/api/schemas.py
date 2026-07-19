from __future__ import annotations

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
