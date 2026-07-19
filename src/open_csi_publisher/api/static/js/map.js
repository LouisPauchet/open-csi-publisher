// Station map: fetches /datasets for fixed-station positions and, per mobile
// dataset, /datasets/{id}/data for a recent latitude/longitude track — reusing
// the same access-controlled REST endpoints rather than the page embedding any
// dataset data server-side. A restricted dataset that /datasets already
// excludes for the current caller simply never appears here either.

const SVALBARD_CENTER = [78.0, 15.0];
const TRACK_LOOKBACK_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

async function initMap() {
  const map = L.map("map").setView(SVALBARD_CENTER, 5);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(map);

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
      addFixedMarker(map, dataset);
    } else if (dataset.platform_type === "mobile") {
      await addMobileTrack(map, dataset);
    }
  }
}

function addFixedMarker(map, dataset) {
  const { lat, lon } = dataset.position;
  if (lat === null || lat === undefined || lon === null || lon === undefined) return;
  L.marker([lat, lon])
    .addTo(map)
    .bindPopup(`<strong>${dataset.title}</strong><br>${dataset.id}`);
}

async function addMobileTrack(map, dataset) {
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

  L.polyline(points, { color: "#2b6cb0" }).addTo(map);
  const last = points[points.length - 1];
  L.marker(last)
    .addTo(map)
    .bindPopup(`<strong>${dataset.title}</strong><br>${dataset.id} (latest position)`);
}

document.addEventListener("DOMContentLoaded", initMap);
