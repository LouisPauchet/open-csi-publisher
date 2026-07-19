// Dataset detail panel: clicking a listing row (or, via map.js, a map
// marker) shows metadata and links to access the dataset — OPeNDAP, NetCDF
// download, CSV download — reusing the exact same REST endpoints already
// built for that purpose rather than duplicating any dataset-building logic
// here. Exposes window.showDatasetPanel() so map.js can call it too.

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".dataset-row").forEach((row) => {
    row.addEventListener("click", () => selectRow(row));
  });
});

function selectRow(row) {
  let metadata = {};
  try {
    metadata = JSON.parse(row.dataset.meta || "{}");
  } catch (err) {
    metadata = {};
  }
  highlightRow(row);
  showDatasetPanel({
    id: row.dataset.id,
    title: row.dataset.title || row.dataset.id,
    platform_type: row.dataset.platformType,
    metadata: metadata,
  });
}

function highlightRow(row) {
  document.querySelectorAll(".dataset-row.selected").forEach((r) => r.classList.remove("selected"));
  row.classList.add("selected");
}

function showDatasetPanel(dataset) {
  const panel = document.getElementById("dataset-panel");
  if (!panel) return;

  const metaItems = Object.entries(dataset.metadata || {})
    .map(([key, value]) => `<li><strong>${escapeHtml(key)}:</strong> ${escapeHtml(String(value))}</li>`)
    .join("");

  const id = encodeURIComponent(dataset.id);
  const opendapUrl = `${window.location.origin}/opendap/datasets/${id}/opendap`;

  panel.innerHTML =
    `<h3>${escapeHtml(dataset.title)}</h3>` +
    `<p><code>${escapeHtml(dataset.id)}</code>` +
    (dataset.platform_type ? ` &middot; ${escapeHtml(dataset.platform_type)}` : "") +
    `</p>` +
    `<ul class="panel-meta">${metaItems}</ul>` +
    `<div class="panel-links">` +
    `<a href="/datasets/${id}" target="_blank" rel="noopener">Full metadata (JSON)</a>` +
    `<a href="/datasets/${id}/deployments" target="_blank" rel="noopener">Deployment history (JSON)</a>` +
    `<a href="/opendap/datasets/${id}/opendap.dds" target="_blank" rel="noopener">View OPeNDAP structure (DDS)</a>` +
    `<span>OPeNDAP URL (open in Panoply / xarray / other DAP clients):</span>` +
    `<code class="panel-opendap-url">${escapeHtml(opendapUrl)}</code>` +
    `<a href="/datasets/${id}/download.nc">Download NetCDF (.nc)</a>` +
    `<a href="/datasets/${id}/download.csv">Download CSV</a>` +
    `</div>`;
  panel.classList.remove("hidden");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

window.showDatasetPanel = showDatasetPanel;
