from __future__ import annotations

from pathlib import Path

PANEL_JS = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "open_csi_publisher"
    / "api"
    / "static"
    / "js"
    / "dataset_panel.js"
)


def test_dataset_panel_js_exists():
    assert PANEL_JS.is_file()


def test_dataset_panel_js_links_to_all_three_access_methods():
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "opendap" in content.lower()
    assert "download.nc" in content
    assert "download.csv" in content


def test_dataset_panel_js_exposes_show_panel_for_map_js_to_call():
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "window.showDatasetPanel" in content


def test_dataset_panel_js_escapes_html_rather_than_interpolating_raw_metadata():
    # metadata values are user/operator-authored config content — must not be
    # interpolated into innerHTML unescaped (a stored-XSS-shaped mistake)
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "escapeHtml" in content


def test_dataset_panel_js_offers_a_date_range_for_downloads():
    content = PANEL_JS.read_text(encoding="utf-8")
    assert 'type="date"' in content
    assert "panel-start" in content
    assert "panel-end" in content


def test_dataset_panel_js_updates_download_links_from_the_date_range():
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "panel-download-nc" in content
    assert "panel-download-csv" in content
    assert "URLSearchParams" in content
    assert "addEventListener" in content
