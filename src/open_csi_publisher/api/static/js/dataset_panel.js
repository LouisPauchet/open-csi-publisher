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

  const metadata = dataset.metadata || {};
  const description = metadata.description || "";
  // description gets its own line above; the metadata list below is the
  // remaining (often long) key/value technical detail, scrolled separately
  // so it can't push the always-visible title/description/links out of view.
  const metaItems = Object.entries(metadata)
    .filter(([key]) => key !== "description")
    .map(([key, value]) => `<li><strong>${escapeHtml(key)}:</strong> ${escapeHtml(String(value))}</li>`)
    .join("");

  const id = encodeURIComponent(dataset.id);
  const opendapUrl = `${window.location.origin}/opendap/datasets/${id}/opendap`;

  panel.innerHTML =
    `<div class="panel-fixed">` +
    `<h3>${escapeHtml(dataset.title)}</h3>` +
    `<p><code>${escapeHtml(dataset.id)}</code>` +
    (dataset.platform_type ? ` &middot; ${escapeHtml(dataset.platform_type)}` : "") +
    `</p>` +
    (description ? `<p class="panel-description">${escapeHtml(description)}</p>` : "") +
    `</div>` +
    `<div class="panel-meta-scroll"><ul class="panel-meta">${metaItems}</ul></div>` +
    `<div class="panel-fixed">` +
    `<div class="panel-dates">` +
    `<label>From <input type="date" class="panel-start"></label>` +
    `<label>To <input type="date" class="panel-end"></label>` +
    `<span class="panel-dates-hint">(leave blank for the full record)</span>` +
    `</div>` +
    `<div class="panel-links">` +
    `<a href="/datasets/${id}" target="_blank" rel="noopener">Full metadata (JSON)</a>` +
    `<a href="/datasets/${id}/deployments" target="_blank" rel="noopener">Deployment history (JSON)</a>` +
    `<a href="/opendap/datasets/${id}/opendap.dds" target="_blank" rel="noopener">View OPeNDAP structure (DDS)</a>` +
    `<span>OPeNDAP URL (open in Panoply / xarray / other DAP clients):</span>` +
    `<code class="panel-opendap-url">${escapeHtml(opendapUrl)}</code>` +
    `<a class="panel-download-nc" href="/datasets/${id}/download.nc">Download NetCDF (.nc)</a>` +
    `<a class="panel-download-csv" href="/datasets/${id}/download.csv">Download CSV</a>` +
    `</div>` +
    `</div>`;
  panel.classList.remove("hidden");

  wireDateRangeToDownloadLinks(panel, id);
}

// The date inputs update the download links' href on every change, so the
// links always reflect whatever range is currently selected — no separate
// "apply" step, and the links still work perfectly well with no dates chosen
// (full record, matching download.nc/.csv's own start/end-optional design).
function wireDateRangeToDownloadLinks(panel, encodedId) {
  const startInput = panel.querySelector(".panel-start");
  const endInput = panel.querySelector(".panel-end");
  const ncLink = panel.querySelector(".panel-download-nc");
  const csvLink = panel.querySelector(".panel-download-csv");

  function update() {
    const params = new URLSearchParams();
    if (startInput.value) params.set("start", startInput.value);
    if (endInput.value) params.set("end", endInput.value);
    const query = params.toString();
    ncLink.href = `/datasets/${encodedId}/download.nc` + (query ? `?${query}` : "");
    csvLink.href = `/datasets/${encodedId}/download.csv` + (query ? `?${query}` : "");
  }

  startInput.addEventListener("change", update);
  endInput.addEventListener("change", update);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

window.showDatasetPanel = showDatasetPanel;
