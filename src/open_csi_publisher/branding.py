from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class BrandingConfig(BaseModel):
    """Visual identity for the portal: logo and color set, kept out of code so
    a non-UNIS deployment can swap them out via settings.branding_file rather
    than editing templates/CSS (the same config-driven-everything approach
    already used for data sources, applied to look-and-feel).

    Defaults here are deliberately plain/generic, not UNIS's own palette —
    they're what a fresh non-UNIS deployment sees before writing its own
    branding.yaml. The real UNIS values live in sample_configs/branding.yaml,
    the file settings.branding_file points at by default.
    """

    model_config = ConfigDict(extra="forbid")

    site_name: str = "Environmental Data Portal"
    logo_url: str | None = None
    color_primary: str = "#1B4965"
    color_secondary: str = "#22333B"
    color_background: str = "#FFFFFF"
    color_header_background: str = "#F4F6F5"
    color_link: str = "#1B4965"
    color_link_hover: str = "#0E2A38"
    color_border: str = "#D0D5DA"
    font_family: str = 'system-ui, -apple-system, "Segoe UI", sans-serif'
    radius: str = "6px"


def load_branding(path: Path) -> BrandingConfig:
    if not path.is_file():
        return BrandingConfig()
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return BrandingConfig.model_validate(doc)
