from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from open_csi_publisher.api.auth import User, get_current_user
from open_csi_publisher.api.deps import get_branding
from open_csi_publisher.branding import BrandingConfig
from open_csi_publisher.core.config_schema import DatasetConfig
from open_csi_publisher.settings import settings

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/config-validator")
def config_validator_page(
    request: Request,
    branding: BrandingConfig = Depends(get_branding),
    user: User | None = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "config_validator.html",
        {"branding": branding, "user": user, "oidc_enabled": settings.oidc_configured},
    )


@router.post("/config-validator/validate")
async def validate_config(request: Request) -> dict[str, Any]:
    """Paste-a-config-get-a-summary-or-errors, reusing `DatasetConfig` itself (not a
    reimplementation of its rules) so this always reflects the exact same validation
    `open-csi-config` and the running server apply — including model-level rules
    (deployment ordering, mobile lat/lon variable requirements, extra_dimension
    consistency, raw-column collisions), not just field types.
    """
    body = await request.body()
    try:
        raw = json.loads(body)
    except json.JSONDecodeError as exc:
        return {"valid": False, "errors": [f"Invalid JSON: {exc}"], "summary": None}

    if not isinstance(raw, dict):
        return {"valid": False, "errors": ["Config must be a JSON object"], "summary": None}

    try:
        config = DatasetConfig.model_validate(raw)
    except ValidationError as exc:
        return {"valid": False, "errors": _format_errors(exc), "summary": None}

    return {"valid": True, "errors": [], "summary": _summarize(config)}


def _format_errors(exc: ValidationError) -> list[str]:
    messages = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"]) or "(config)"
        messages.append(f"{loc}: {error['msg']}")
    return messages


def _summarize(config: DatasetConfig) -> dict[str, Any]:
    return {
        "id": config.id,
        "title": config.metadata.title,
        "platform_type": config.platform_type,
        "access": config.access,
        "source_type": config.source_type,
        "metadata": {k: v for k, v in config.metadata.model_dump().items() if v is not None},
        "source_config": config.source_config.model_dump(),
        "output": config.output.model_dump(),
        "variables": [
            {
                "name": v.canonical_name,
                "standard_name": v.standard_name,
                "units": v.units,
                "dtype": v.dtype,
                "raw_names": v.all_raw_names(),
                "extra_dimension": (
                    [d.model_dump() for d in v.extra_dimension] if v.extra_dimension else None
                ),
            }
            for v in config.variables
        ],
        "deployments": [
            {
                "start": d.start.isoformat(),
                "end": d.end.isoformat() if d.end else None,
                "lat": d.lat,
                "lon": d.lon,
                "elevation": d.elevation,
                "platform_name": d.platform_name,
                "instrument_config": d.instrument_config,
                "notes": d.notes,
            }
            for d in config.deployments
        ],
    }
