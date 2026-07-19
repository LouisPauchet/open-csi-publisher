// Progressive enhancement only: the server-rendered page already reflects the
// current query-string filters and works with this script absent. This just
// mirrors the same filter semantics (api/services.py::_matches) client-side
// for instant feedback, hiding/showing rows already present in the DOM rather
// than fetching or deleting anything — a restricted dataset that was never
// rendered for this caller can never be "un-hidden" by this script.
function applyFilters() {
  const form = document.getElementById("filter-form");
  if (!form) return;

  const q = form.q.value.trim().toLowerCase();
  const platformType = form.platform_type.value;
  const standardName = form.standard_name.value;
  const metaKey = form.meta_key.value;
  const metaValue = form.meta_value.value.trim().toLowerCase();

  document.querySelectorAll(".dataset-row").forEach((row) => {
    let visible = true;

    if (q && !(row.dataset.search || "").includes(q)) {
      visible = false;
    }

    if (visible && platformType && row.dataset.platformType !== platformType) {
      visible = false;
    }

    if (visible && standardName) {
      const names = (row.dataset.standardNames || "").split(",");
      if (!names.includes(standardName)) visible = false;
    }

    if (visible && metaKey && metaValue) {
      let meta = {};
      try {
        meta = JSON.parse(row.dataset.meta || "{}");
      } catch (err) {
        meta = {};
      }
      const actual = meta[metaKey];
      if (actual === undefined || !String(actual).toLowerCase().includes(metaValue)) {
        visible = false;
      }
    }

    row.classList.toggle("hidden", !visible);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("filter-form");
  if (!form) return;
  form.addEventListener("input", applyFilters);
  form.addEventListener("change", applyFilters);
});
