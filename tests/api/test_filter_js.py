from __future__ import annotations

from pathlib import Path

FILTER_JS = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "open_csi_publisher"
    / "api"
    / "static"
    / "js"
    / "filter.js"
)


def test_filter_js_exists():
    assert FILTER_JS.is_file()


def test_filter_js_reads_the_same_data_attributes_the_template_renders():
    content = FILTER_JS.read_text(encoding="utf-8")
    # camelCase dataset property names correspond to the template's
    # data-search / data-platform-type / data-standard-names / data-meta attrs
    for marker in ("dataset.search", "dataset.platformType", "dataset.standardNames", "dataset.meta"):
        assert marker in content


def test_filter_js_reads_all_filter_form_fields():
    content = FILTER_JS.read_text(encoding="utf-8")
    for field in ("form.q", "form.platform_type", "form.standard_name", "form.meta_key", "form.meta_value"):
        assert field in content


def test_filter_js_toggles_hidden_class_not_removes_rows():
    # server-rendered rows must stay in the DOM (JS only hides/shows what the
    # server already decided to send) — never re-fetches or deletes anything
    content = FILTER_JS.read_text(encoding="utf-8")
    assert "hidden" in content
    assert "fetch(" not in content
