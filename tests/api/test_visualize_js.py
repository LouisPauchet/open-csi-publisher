from __future__ import annotations

from pathlib import Path

VISUALIZE_JS = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "open_csi_publisher"
    / "api"
    / "static"
    / "js"
    / "visualize.js"
)


def test_visualize_js_exists():
    assert VISUALIZE_JS.is_file()


def test_visualize_js_wraps_its_contents_in_an_iife_to_avoid_global_collisions():
    # Same convention established for map.js/dataset_panel.js (commit
    # 15101a9): plain <script> tags share the global scope, so top-level
    # declarations here must not risk colliding with theirs if this file is
    # ever loaded alongside them.
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert content.rstrip().endswith("})();")
    iife_open = content.index("(function () {") if "(function () {" in content else content.index("(function() {")
    assert content.index('const BASE_PATH = window.APP_ROOT_PATH || "";') > iife_open


def test_visualize_js_fetches_dataset_detail_and_data_endpoints():
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert "fetch(" in content
    assert "/datasets/" in content
    assert "/data" in content


def test_visualize_js_only_offers_numeric_variables():
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert 'dtype === "numeric"' in content


def test_visualize_js_defaults_to_a_bounded_recent_window():
    # This branch has no server-side size cap/timeout on build_dataset() —
    # the page must not rely on one existing; a blank/missing date range
    # must still resolve to a bounded window, not "fetch the full history".
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert "30 * 24 * 60 * 60 * 1000" in content


def test_visualize_js_groups_variables_onto_axes_by_units():
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert "yAxisID" in content
    assert "data-units" in content or "dataset.units" in content


def test_visualize_js_matches_exploded_extra_dimension_columns():
    # core/export.py::to_wide_dataframe explodes an extra_dimension variable
    # into "<name>_<segment>" columns — a naive body[name] lookup would
    # silently drop that variable's data.
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert "startsWith(" in content


def test_visualize_js_escapes_html_rather_than_interpolating_raw_values():
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert "escapeHtml" in content


def test_visualize_js_does_not_reference_an_external_cdn():
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    for marker in ("cdn.", "unpkg", "jsdelivr", "googleapis", "api_key", "apikey"):
        assert marker not in content.lower()


def test_visualize_js_prefixes_every_url_with_the_configured_root_path():
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert 'const BASE_PATH = window.APP_ROOT_PATH || "";' in content


def test_visualize_js_offers_a_manual_axis_range_override():
    # Chart.js's auto-scaled range gets squashed flat by a single sensor
    # fill/error-value outlier — a manual min/max override per axis lets the
    # user clamp the view themselves rather than requiring server/client
    # outlier-filtering heuristics.
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert "axisRangeOverrides" in content
    assert "viz-axis-min" in content
    assert "viz-axis-max" in content


def test_visualize_js_axis_range_override_persists_without_a_refetch():
    # Adjusting the range shouldn't need a new network round-trip — the last
    # fetched response is cached and just re-rendered.
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert "lastBody" in content


def test_visualize_js_enables_wheel_zoom_and_drag_pan():
    # chartjs-plugin-zoom auto-registers itself once its <script> tag loads
    # (confirmed against the real vendored build) -- no Chart.register() call
    # needed here, just the plugin-specific chart config.
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert "zoom:" in content
    assert "wheel:" in content
    assert "pan:" in content


def test_visualize_js_wires_a_reset_zoom_button():
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert "viz-reset-zoom" in content
    assert "resetZoom" in content


def test_visualize_js_formats_and_caps_x_axis_time_labels():
    # Raw ISO datetime strings ("2026-07-10T00:18:10") as category-scale
    # labels are unreadably dense and ugly once rotated — ticks are
    # reformatted to a short label and capped to a fixed count regardless of
    # how many points are plotted.
    content = VISUALIZE_JS.read_text(encoding="utf-8")
    assert "maxTicksLimit" in content
    assert "formatTimeLabel" in content
    assert "getLabelForValue" in content
