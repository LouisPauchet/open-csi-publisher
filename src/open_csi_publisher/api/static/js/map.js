// Station map. Two modes, auto-detected:
//  - Embedded on the listing page (.dataset-row elements present): builds
//    markers directly from the already-rendered, already-filtered rows -
//    no extra /datasets fetch, and automatically consistent with whatever
//    server-side filters are active (a restricted dataset the listing
//    already excluded was never rendered as a row, so it can't appear here
//    either).
//  - Standalone /map page (no rows on the page): fetches /datasets itself.
// Mobile-platform tracks always need a separate fetch either way, since
// position isn't in a row's data-* attributes (it's real per-timestep data,
// not config) - see addMobileTrack().
//
// Marker clicks call window.showDatasetPanel(...) when that's been loaded
// (the listing page includes dataset_panel.js; the standalone map page
// doesn't have to).

const SVALBARD_CENTER = [78.0, 15.0];
const TRACK_LOOKBACK_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

let mapInstance = null;
const markersByDatasetId = {};

async function initMap() {
  mapInstance = L.map("map").setView(SVALBARD_CENTER, 5);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(mapInstance);

  const rows = document.querySelectorAll(".dataset-row");
  if (rows.length > 0) {
    await initFromRenderedRows(rows);
  } else {
    await initFromDatasetsEndpoint();
  }
}

async function initFromRenderedRows(rows) {
  for (const row of rows) {
    const dataset = datasetFromRow(row);
    if (row.dataset.lat !== undefined && row.dataset.lon !== undefined) {
      addFixedMarker(dataset, parseFloat(row.dataset.lat), parseFloat(row.dataset.lon));
    } else if (dataset.platform_type === "mobile") {
      await addMobileTrack(dataset);
    }
  }
}

async function initFromDatasetsEndpoint() {
  let datasets = [];
  try {
    const response = await fetch("/datasets");
    const body = await response.json();
    datasets = body.datasets || [];
  } catch (err) {
    return;
  }

  for (const dataset of datasets) {
    if (dataset.platform_type === "fixed" && dataset.position) {
      addFixedMarker(dataset, dataset.position.lat, dataset.position.lon);
    } else if (dataset.platform_type === "mobile") {
      await addMobileTrack(dataset);
    }
  }
}

function datasetFromRow(row) {
  let metadata = {};
  try {
    metadata = JSON.parse(row.dataset.meta || "{}");
  } catch (err) {
    metadata = {};
  }
  return {
    id: row.dataset.id,
    title: row.dataset.title || row.dataset.id,
    platform_type: row.dataset.platformType,
    metadata: metadata,
  };
}

function addFixedMarker(dataset, lat, lon) {
  if (lat === null || lat === undefined || isNaN(lat) || lon === null || lon === undefined || isNaN(lon)) {
    return;
  }
  const marker = L.marker([lat, lon]).addTo(mapInstance);
  marker.bindPopup(`<strong>${dataset.title}</strong><br>${dataset.id}`);
  marker.on("click", () => selectDataset(dataset));
  markersByDatasetId[dataset.id] = marker;
}

async function addMobileTrack(dataset) {
  const since = new Date(Date.now() - TRACK_LOOKBACK_MS).toISOString();
  const url =
    `/datasets/${encodeURIComponent(dataset.id)}/data` +
    `?variables=latitude&variables=longitude&start=${encodeURIComponent(since)}`;

  let body;
  try {
    const response = await fetch(url);
    if (!response.ok) return;
    body = await response.json();
  } catch (err) {
    return;
  }

  const lats = body.latitude || [];
  const lons = body.longitude || [];
  const points = [];
  for (let i = 0; i < lats.length; i++) {
    if (lats[i] === null || lons[i] === null) continue;
    points.push([lats[i], lons[i]]);
  }
  if (points.length === 0) return;

  L.polyline(points, { color: "#2b6cb0" }).addTo(mapInstance);
  const last = points[points.length - 1];
  const marker = L.marker(last).addTo(mapInstance);
  marker.bindPopup(`<strong>${dataset.title}</strong><br>${dataset.id} (latest position)`);
  marker.on("click", () => selectDataset(dataset));
  markersByDatasetId[dataset.id] = marker;
}

function selectDataset(dataset) {
  if (typeof window.showDatasetPanel === "function") {
    window.showDatasetPanel(dataset);
  }
}

// Called by filter.js after it hides/shows rows, so markers for
// client-side-filtered-out datasets disappear too. Safe no-op if the map
// hasn't finished loading yet or a dataset has no marker (e.g. no position).
function syncMapMarkersWithRows() {
  if (!mapInstance) return;
  document.querySelectorAll(".dataset-row").forEach((row) => {
    const marker = markersByDatasetId[row.dataset.id];
    if (!marker) return;
    const visible = !row.classList.contains("hidden");
    const onMap = mapInstance.hasLayer(marker);
    if (visible && !onMap) marker.addTo(mapInstance);
    if (!visible && onMap) mapInstance.removeLayer(marker);
  });
}
window.syncMapMarkersWithRows = syncMapMarkersWithRows;

document.addEventListener("DOMContentLoaded", initMap);
