from __future__ import annotations

from pathlib import Path

MAP_JS = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "open_csi_publisher"
    / "api"
    / "static"
    / "js"
    / "map.js"
)


def test_map_js_exists():
    assert MAP_JS.is_file()


def test_map_js_fetches_the_datasets_endpoint():
    content = MAP_JS.read_text(encoding="utf-8")
    assert "/datasets" in content
    assert "fetch(" in content


def test_map_js_fetches_mobile_position_via_the_data_endpoint():
    content = MAP_JS.read_text(encoding="utf-8")
    assert "latitude" in content and "longitude" in content
    assert "/data" in content


def test_map_js_does_not_reference_an_external_tile_or_map_api_key():
    content = MAP_JS.read_text(encoding="utf-8")
    for marker in ("mapbox", "googleapis", "api_key", "apikey", "YOUR_API_KEY"):
        assert marker not in content.lower()


def test_map_js_prefixes_every_url_with_the_configured_root_path():
    # window.APP_ROOT_PATH (set by base.html from Settings.root_path) must
    # prefix every root-relative URL this file builds, or every fetch breaks
    # once the app is mounted under a subpath.
    content = MAP_JS.read_text(encoding="utf-8")
    assert 'const BASE_PATH = window.APP_ROOT_PATH || "";' in content
    assert 'fetch(BASE_PATH + "/datasets")' in content
    assert "`${BASE_PATH}/datasets/${encodeURIComponent(dataset.id)}/data`" in content


def test_map_js_draws_a_bounding_box_not_a_full_track_polyline():
    # A dense/long-history mobile station's full per-point track is heavy to
    # render (thousands of vertices) — addMobileTrack() must draw a
    # lat/lon-min/max bounding box instead of every fetched point.
    content = MAP_JS.read_text(encoding="utf-8")
    assert "L.polyline(points" not in content
    assert "L.rectangle(" in content


def test_map_js_computes_lat_lon_bounds_from_fetched_points():
    content = MAP_JS.read_text(encoding="utf-8")
    assert "Math.min(...latValues)" in content
    assert "Math.max(...latValues)" in content
    assert "Math.min(...lonValues)" in content
    assert "Math.max(...lonValues)" in content


def test_map_js_skips_the_rectangle_for_a_degenerate_single_point():
    # A stationary/near-stationary mobile platform (or exactly one fetched
    # point) has no real extent — the marker alone already conveys that;
    # drawing a zero-area rectangle on top of it would add nothing.
    content = MAP_JS.read_text(encoding="utf-8")
    assert "latMin !== latMax || lonMin !== lonMax" in content


def test_map_js_wraps_its_contents_in_an_iife_to_avoid_global_collisions():
    # map.js and dataset_panel.js are both loaded as plain, non-module
    # <script> tags on the listing page (list.html) and therefore share the
    # global scope. Without each file scoping its own top-level declarations
    # (BASE_PATH, mapInstance, etc.) inside an IIFE, both files' identical
    # `const BASE_PATH = ...` collide: "Uncaught SyntaxError: Identifier
    # 'BASE_PATH' has already been declared" — which aborts the *second*
    # script's execution entirely (a SyntaxError happens at parse time), so
    # dataset_panel.js never runs and window.showDatasetPanel is never
    # defined, silently breaking every row's click handler.
    content = MAP_JS.read_text(encoding="utf-8")
    assert content.rstrip().endswith("})();")
    iife_open = content.index("(function () {") if "(function () {" in content else content.index("(function() {")
    # the real declaration (with its actual RHS, unlike the explanatory
    # comment above the IIFE which mentions "const BASE_PATH = ..." in prose)
    # must come after the IIFE opens, not at top level
    assert content.index('const BASE_PATH = window.APP_ROOT_PATH || "";') > iife_open
