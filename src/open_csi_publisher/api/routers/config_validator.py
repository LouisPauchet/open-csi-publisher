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


def _template_context(request: Request) -> dict:
    """Injected into every render so templates can prefix hrefs/src with the
    configured ROOT_PATH (Settings.root_path) instead of hardcoding a
    domain-root-relative path. Read from `settings` directly, not
    `request.scope["root_path"]` (ASGI root_path) — see api/app.py's
    create_app() docstring for why this app never sets that."""
    return {"root_path": settings.root_path}


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR), context_processors=[_template_context])


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
    text = (await request.body()).decode("utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "valid": False,
            "errors": [{"loc": None, "msg": f"Invalid JSON: {exc.msg}", "line": exc.lineno}],
            "summary": None,
        }

    if not isinstance(raw, dict):
        return {
            "valid": False,
            "errors": [{"loc": None, "msg": "Config must be a JSON object", "line": 1}],
            "summary": None,
        }

    try:
        config = DatasetConfig.model_validate(raw)
    except ValidationError as exc:
        line_map = _LineMapper(text).build()
        return {"valid": False, "errors": _format_errors(exc, line_map), "summary": None}

    return {"valid": True, "errors": [], "summary": _summarize(config)}


def _format_errors(exc: ValidationError, line_map: dict[tuple, int]) -> list[dict[str, Any]]:
    errors = []
    for error in exc.errors():
        loc = tuple(error["loc"])
        errors.append(
            {
                "loc": ".".join(str(part) for part in loc) or None,
                "msg": error["msg"],
                "line": _nearest_line(loc, line_map),
            }
        )
    return errors


def _nearest_line(loc: tuple, line_map: dict[tuple, int]) -> int | None:
    """The map only has entries for paths that actually appear in the source text
    (a required field that's simply absent, e.g., was never parsed into it) — walk
    up to the nearest ancestor path that does, so every error still gets a line to
    jump to, even one about something missing. `()` (the top-level object) is
    always present, so this never falls through to None for a well-formed body.
    """
    for end in range(len(loc), -1, -1):
        line = line_map.get(loc[:end])
        if line is not None:
            return line
    return None


class _LineMapper:
    """Maps each JSON pointer path (tuple of object keys / array indices) to the
    1-based line its value starts on, by walking the same token stream a JSON
    parser would — used to point a `pydantic` error's `loc` (a logical path, not
    a text position) back at an actual line in the pasted text. Only ever run on
    text `json.loads` has already parsed successfully, so this doesn't need to
    handle malformed JSON itself.
    """

    def __init__(self, text: str):
        self._text = text
        self._i = 0
        self._line_map: dict[tuple, int] = {}

    def build(self) -> dict[tuple, int]:
        self._skip_ws()
        self._line_map[()] = self._line_at(self._i)
        self._parse_value(())
        return self._line_map

    def _line_at(self, pos: int) -> int:
        return self._text.count("\n", 0, pos) + 1

    def _skip_ws(self) -> None:
        while self._i < len(self._text) and self._text[self._i] in " \t\r\n":
            self._i += 1

    def _parse_value(self, path: tuple) -> None:
        self._skip_ws()
        c = self._text[self._i]
        if c == "{":
            self._parse_object(path)
        elif c == "[":
            self._parse_array(path)
        elif c == '"':
            self._parse_string()
        else:
            self._parse_scalar()

    def _parse_object(self, path: tuple) -> None:
        self._i += 1  # '{'
        self._skip_ws()
        if self._text[self._i] == "}":
            self._i += 1
            return
        while True:
            self._skip_ws()
            key_start = self._i
            key = self._parse_string()
            self._skip_ws()
            self._i += 1  # ':'
            child = path + (key,)
            self._line_map[child] = self._line_at(key_start)
            self._parse_value(child)
            self._skip_ws()
            if self._text[self._i] == ",":
                self._i += 1
                continue
            self._i += 1  # '}'
            return

    def _parse_array(self, path: tuple) -> None:
        self._i += 1  # '['
        self._skip_ws()
        if self._text[self._i] == "]":
            self._i += 1
            return
        index = 0
        while True:
            self._skip_ws()
            child = path + (index,)
            self._line_map[child] = self._line_at(self._i)
            self._parse_value(child)
            index += 1
            self._skip_ws()
            if self._text[self._i] == ",":
                self._i += 1
                continue
            self._i += 1  # ']'
            return

    def _parse_string(self) -> str:
        start = self._i
        self._i += 1
        while self._text[self._i] != '"':
            if self._text[self._i] == "\\":
                self._i += 1
            self._i += 1
        self._i += 1
        return json.loads(self._text[start : self._i])

    def _parse_scalar(self) -> None:
        while self._i < len(self._text) and self._text[self._i] not in ",}] \t\r\n":
            self._i += 1


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
