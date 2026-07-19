// Dataset detail panel: clicking a listing row (or, via map.js, a map
// marker) shows metadata and compact icon buttons to access the dataset —
// OPeNDAP, NetCDF/CSV download, metadata + deployment history JSON — reusing
// the exact same REST endpoints already built for that purpose rather than
// duplicating any dataset-building logic here. Exposes window.showDatasetPanel()
// so map.js can call it too.

const ICON_DOWNLOAD =
  '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" ' +
  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>';

const ICON_LINK =
  '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" ' +
  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<circle cx="7" cy="12" r="3"/><circle cx="17" cy="12" r="3"/><path d="M10 12h4"/></svg>';

const ICON_DOCUMENT =
  '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" ' +
  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M6 2h9l5 5v15H6z"/><path d="M15 2v5h5"/><path d="M9 13h6"/><path d="M9 17h6"/></svg>';

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".dataset-row").forEach((row) => {
    row.addEventListener("click", () => selectRow(row));
  });
});

// Registered once for the page's lifetime (not per showDatasetPanel call,
// which would otherwise pile up one extra document-level listener per
// dataset selected) — closes any open popover on an outside click. A click
// on the toggle button or inside an open popover's own content is exempt:
// its target is still within .panel-action, which the button's own click
// handler (see wirePanelPopovers) already resolved first, earlier in the
// same bubbling phase.
document.addEventListener("click", (event) => {
  if (event.target.closest(".panel-action")) return;
  closeAllPopovers();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeAllPopovers();
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
  // description gets its own line; the metadata list below is the remaining
  // (often long) key/value technical detail, scrolled separately so it can't
  // push the always-visible title/actions/description out of view.
  const metaItems = Object.entries(metadata)
    .filter(([key]) => key !== "description")
    .map(([key, value]) => `<li><strong>${escapeHtml(key)}:</strong> ${escapeHtml(String(value))}</li>`)
    .join("");

  const id = encodeURIComponent(dataset.id);
  const opendapUrl = `${window.location.origin}/opendap/datasets/${id}/opendap`;

  panel.innerHTML =
    `<div class="panel-fixed">` +
    `<h3>${escapeHtml(dataset.title)}</h3>` +
    `<div class="panel-actions">` +
    `<div class="panel-action">` +
    `<button type="button" class="panel-action-btn panel-download-btn" aria-haspopup="true" aria-expanded="false" title="Download data">${ICON_DOWNLOAD}</button>` +
    `<div class="panel-popover panel-download-popover hidden">` +
    `<div class="panel-dates">` +
    `<label>From <input type="date" class="panel-start"></label>` +
    `<label>To <input type="date" class="panel-end"></label>` +
    `<span class="panel-dates-hint">(leave blank for the full record)</span>` +
    `</div>` +
    `<div class="panel-download-formats">` +
    `<a class="panel-download-nc" href="/datasets/${id}/download.nc">NetCDF (.nc)</a>` +
    `<a class="panel-download-csv" href="/datasets/${id}/download.csv">CSV</a>` +
    `</div>` +
    `</div>` +
    `</div>` +
    `<div class="panel-action">` +
    `<button type="button" class="panel-action-btn panel-opendap-btn" aria-haspopup="true" aria-expanded="false" title="OPeNDAP access">${ICON_LINK}</button>` +
    `<div class="panel-popover panel-opendap-popover hidden">` +
    `<span>OPeNDAP URL (open in Panoply / xarray / other DAP clients):</span>` +
    `<div class="panel-opendap-copy-row">` +
    `<code class="panel-opendap-url">${escapeHtml(opendapUrl)}</code>` +
    `<button type="button" class="panel-opendap-copy">Copy</button>` +
    `</div>` +
    `<a href="/opendap/datasets/${id}/opendap.dds" target="_blank" rel="noopener">View OPeNDAP structure (DDS)</a>` +
    `</div>` +
    `</div>` +
    `<div class="panel-action">` +
    `<button type="button" class="panel-action-btn panel-json-btn" aria-haspopup="true" aria-expanded="false" title="Metadata &amp; deployment history (JSON)">${ICON_DOCUMENT}</button>` +
    `<div class="panel-popover panel-json-popover hidden">` +
    `<a href="/datasets/${id}" target="_blank" rel="noopener">Full metadata (JSON)</a>` +
    `<a href="/datasets/${id}/deployments" target="_blank" rel="noopener">Deployment history (JSON)</a>` +
    `</div>` +
    `</div>` +
    `</div>` +
    `<p><code>${escapeHtml(dataset.id)}</code>` +
    (dataset.platform_type ? ` &middot; ${escapeHtml(dataset.platform_type)}` : "") +
    `</p>` +
    (description ? `<p class="panel-description">${escapeHtml(description)}</p>` : "") +
    `</div>` +
    `<div class="panel-meta-scroll"><ul class="panel-meta">${metaItems}</ul></div>`;
  panel.classList.remove("hidden");

  wireDateRangeToDownloadLinks(panel, id);
  wirePanelPopovers(panel);
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

// Each icon button toggles its own popover, closing any other open one
// first. Freshly wired every showDatasetPanel() call since panel.innerHTML
// just replaced the buttons (and their old listeners) entirely.
function wirePanelPopovers(panel) {
  panel.querySelectorAll(".panel-action").forEach((action) => {
    const button = action.querySelector(".panel-action-btn");
    const popover = action.querySelector(".panel-popover");
    button.addEventListener("click", () => {
      const isOpen = !popover.classList.contains("hidden");
      closeAllPopovers();
      if (!isOpen) {
        popover.classList.remove("hidden");
        button.setAttribute("aria-expanded", "true");
      }
    });
  });

  const copyButton = panel.querySelector(".panel-opendap-copy");
  if (copyButton) {
    copyButton.addEventListener("click", () => {
      const url = panel.querySelector(".panel-opendap-url").textContent;
      copyToClipboard(url, copyButton);
    });
  }
}

function closeAllPopovers() {
  document.querySelectorAll("#dataset-panel .panel-popover").forEach((popover) => {
    popover.classList.add("hidden");
  });
  document.querySelectorAll("#dataset-panel .panel-action-btn").forEach((button) => {
    button.setAttribute("aria-expanded", "false");
  });
}

function copyToClipboard(text, button) {
  if (!navigator.clipboard || !navigator.clipboard.writeText) return;
  navigator.clipboard.writeText(text).then(() => {
    const original = button.textContent;
    button.textContent = "Copied!";
    setTimeout(() => {
      button.textContent = original;
    }, 1500);
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

window.showDatasetPanel = showDatasetPanel;
