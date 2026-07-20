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


def test_dataset_panel_js_shows_description_separately_from_the_metadata_list():
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "panel-description" in content
    assert 'key !== "description"' in content


def test_dataset_panel_js_only_scrolls_the_metadata_list():
    # title/description stay in a "panel-fixed" block; only "panel-meta-scroll"
    # (the metadata <ul>) is meant to scroll — see the matching
    # #dataset-panel .panel-meta-scroll rule in site.css
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "panel-fixed" in content
    assert "panel-meta-scroll" in content


def test_dataset_panel_js_shows_three_compact_action_icons_after_the_title():
    # Download, OPeNDAP, and metadata/deployments (JSON) are each a single
    # icon button, not long inline links — collapsed so the panel doesn't eat
    # vertical space that the (often long) metadata list needs.
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "panel-actions" in content
    assert "panel-download-btn" in content
    assert "panel-opendap-btn" in content
    assert "panel-json-btn" in content
    # the actions row is built into the same fixed block as the <h3>, right
    # after it, before the id/platform-type line and description
    title_pos = content.index("<h3>")
    actions_pos = content.index("panel-actions")
    id_line_pos = content.index("escapeHtml(dataset.id)")
    assert title_pos < actions_pos < id_line_pos


def test_dataset_panel_js_download_popover_offers_dates_and_both_formats():
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "panel-download-popover" in content
    assert "panel-start" in content
    assert "panel-end" in content
    assert "panel-download-nc" in content
    assert "panel-download-csv" in content


def test_dataset_panel_js_opendap_popover_offers_a_copy_button():
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "panel-opendap-popover" in content
    assert "panel-opendap-copy" in content
    assert "clipboard" in content.lower()


def test_dataset_panel_js_json_popover_links_metadata_and_deployment_history():
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "panel-json-popover" in content
    assert "/deployments" in content


def test_dataset_panel_js_popovers_start_hidden_and_close_on_outside_click():
    content = PANEL_JS.read_text(encoding="utf-8")
    assert '"panel-popover panel-download-popover hidden"' in content
    assert "closeAllPopovers" in content


def test_dataset_panel_js_fetches_full_metadata_after_the_initial_render():
    # renderPanel(dataset) runs synchronously first (so the panel is never
    # left empty during the round-trip); fetchFullMetadata() then hits the
    # detail endpoint for everything build_dataset() computes that isn't
    # cheap enough to embed in every listing row (provenance, geospatial/
    # time coverage) and re-renders once it lands.
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "fetchFullMetadata" in content
    assert "fetch(`/datasets/" in content
    assert "detail.metadata" in content


def test_dataset_panel_js_guards_against_a_stale_fetch_response():
    # if the user clicks a different row before the fetch for the first one
    # resolves, the late response must not clobber the panel that's now
    # showing a different dataset
    content = PANEL_JS.read_text(encoding="utf-8")
    assert "selectedId" in content
