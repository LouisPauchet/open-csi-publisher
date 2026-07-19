from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from open_csi_publisher.branding import BrandingConfig, load_branding

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BRANDING_FILE = REPO_ROOT / "sample_configs" / "branding.yaml"


def test_branding_config_has_sensible_generic_defaults():
    # No file, no deployment-specific configuration: still a usable, coherent
    # (if plain) color set and no logo — this is what a non-UNIS deployer sees
    # before writing their own branding.yaml.
    branding = BrandingConfig()
    assert branding.logo_url is None
    assert branding.site_name
    assert branding.color_primary.startswith("#")
    assert branding.color_link.startswith("#")
    # no separate heading font by default — headings just inherit body text
    assert branding.heading_font_family == "inherit"


def test_default_branding_file_uses_unis_website_fonts():
    # unis.no's own theme (vars.css): IBM Plex Sans for body text, Adamina
    # (serif) for headings — see docs/branding.md for the source.
    branding = load_branding(DEFAULT_BRANDING_FILE)
    assert "IBM Plex Sans" in branding.font_family
    assert "Adamina" in branding.heading_font_family


def test_load_branding_returns_defaults_when_file_missing(tmp_path):
    branding = load_branding(tmp_path / "does_not_exist.yaml")
    assert branding == BrandingConfig()


def test_load_branding_parses_a_yaml_file(tmp_path):
    path = tmp_path / "branding.yaml"
    path.write_text(
        "site_name: Test Portal\n"
        "logo_url: https://example.org/logo.svg\n"
        "color_primary: '#123456'\n",
        encoding="utf-8",
    )
    branding = load_branding(path)
    assert branding.site_name == "Test Portal"
    assert branding.logo_url == "https://example.org/logo.svg"
    assert branding.color_primary == "#123456"
    # fields not present in the file keep the model's defaults
    assert branding.color_secondary == BrandingConfig().color_secondary


def test_load_branding_rejects_unknown_fields(tmp_path):
    path = tmp_path / "branding.yaml"
    path.write_text("colour_primary: '#123456'\n", encoding="utf-8")  # typo'd key
    with pytest.raises(ValidationError):
        load_branding(path)


def test_default_branding_file_is_unis_branded():
    # sample_configs/branding.yaml is this repo's actual shipped configuration
    # (same pattern as sample_configs/sources.yaml) — a non-UNIS deployer
    # replaces or repoints settings.branding_file, they don't edit this one.
    # site_name is deliberately generic ("Environmental Data Portal"), so the
    # logo + color set (pulled from unis.no's own theme) are what mark this as
    # UNIS-branded, not the name text.
    branding = load_branding(DEFAULT_BRANDING_FILE)
    assert branding.logo_url is not None
    assert branding.logo_url.startswith("https://www.unis.no/")
    assert branding.color_primary == "#006199"
