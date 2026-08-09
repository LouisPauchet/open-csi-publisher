// Data visualization page: pick a dataset, pick one or more of its numeric
// variables, see them plotted as a time series. Reuses the same REST
// endpoints the rest of the app already relies on (GET /datasets/{id} for
// the variable list, GET /datasets/{id}/data for the actual series) — no
// dedicated backend endpoint exists or is needed for this page.
//
// Wrapped in an IIFE per the convention established for map.js/
// dataset_panel.js (commit 15101a9, fixing a real collision when two
// un-wrapped top-level `const BASE_PATH` declarations loaded on the same
// page): this file isn't currently loaded alongside those, but there's no
// reason to reintroduce that risk.
(function () {
  // Set by base.html from Settings.root_path — prefixes every URL below so
  // they still resolve once this app is mounted under a subpath.
  const BASE_PATH = window.APP_ROOT_PATH || "";

  // This branch has no server-side timeout/size cap on build_dataset() (see
  // the separate fix-dataset-build-reliability branch, not merged here) —
  // a blank/missing date range must never mean "fetch full history" on this
  // page; it always falls back to this bounded recent window instead, as
  // this page's own independent safety measure.
  const DEFAULT_LOOKBACK_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

  const AXIS_COLORS = ["#2b6cb0", "#c05621", "#276749", "#805ad5", "#b83280", "#2c7a7b"];

  let chartInstance = null;
  let currentDatasetId = null;

  function init() {
    const datasetSelect = document.getElementById("viz-dataset");
    const startInput = document.getElementById("viz-start");
    const endInput = document.getElementById("viz-end");
    if (!datasetSelect || !startInput || !endInput) return;

    seedDefaultDateRange(startInput, endInput);

    datasetSelect.addEventListener("change", () => {
      if (datasetSelect.value) {
        loadDataset(datasetSelect.value);
      } else {
        currentDatasetId = null;
        clearVariables();
        clearChart();
        setStatus("");
      }
    });
    startInput.addEventListener("change", refreshChart);
    endInput.addEventListener("change", refreshChart);

    // Server-rendered preselection (the ?dataset= deep-link from the
    // dataset panel's Visualize button) — read the already-rendered <select>
    // value rather than inventing a second, JS-facing channel for the same
    // fact (matches datasets/list.html's own filters.* precedent).
    if (datasetSelect.value) {
      loadDataset(datasetSelect.value);
    }
  }

  function seedDefaultDateRange(startInput, endInput) {
    const end = new Date();
    const start = new Date(end.getTime() - DEFAULT_LOOKBACK_MS);
    startInput.value = toDateInputValue(start);
    endInput.value = toDateInputValue(end);
  }

  function toDateInputValue(date) {
    return date.toISOString().slice(0, 10);
  }

  async function loadDataset(id) {
    currentDatasetId = id;
    clearChart();
    setStatus("Loading variables…");

    let detail;
    try {
      const response = await fetch(`${BASE_PATH}/datasets/${encodeURIComponent(id)}`);
      if (!response.ok) {
        setStatus("Could not load this dataset.");
        return;
      }
      detail = await response.json();
    } catch (err) {
      setStatus("Could not load this dataset.");
      return;
    }

    // Only numeric variables are line-chartable — string/status variables
    // (VariableDetail.dtype) aren't offered here.
    const numericVariables = (detail.variables || []).filter((v) => v.dtype === "numeric");
    renderVariables(numericVariables);
    setStatus("");
  }

  function renderVariables(variables) {
    const container = document.getElementById("viz-variables");
    if (!container) return;

    if (variables.length === 0) {
      container.innerHTML = '<p class="viz-placeholder">No numeric variables in this dataset.</p>';
      return;
    }

    container.innerHTML = variables
      .map((v) => {
        const label = v.units ? `${v.name} (${v.units})` : v.name;
        return (
          `<label>` +
          `<input type="checkbox" class="viz-variable-checkbox" value="${escapeHtml(v.name)}" data-units="${escapeHtml(v.units || "")}">` +
          `${escapeHtml(label)}` +
          `</label>`
        );
      })
      .join("");

    container.querySelectorAll(".viz-variable-checkbox").forEach((checkbox) => {
      checkbox.addEventListener("change", refreshChart);
    });
  }

  function clearVariables() {
    const container = document.getElementById("viz-variables");
    if (container) {
      container.innerHTML = '<p class="viz-placeholder">Choose a dataset to see its numeric variables.</p>';
    }
  }

  function checkedVariableCheckboxes() {
    return Array.from(document.querySelectorAll(".viz-variable-checkbox:checked"));
  }

  async function refreshChart() {
    if (!currentDatasetId) return;

    const checked = checkedVariableCheckboxes();
    if (checked.length === 0) {
      clearChart();
      setStatus("Choose at least one variable to plot.");
      return;
    }

    const { start, end } = resolveDateRange();
    const params = new URLSearchParams();
    checked.forEach((checkbox) => params.append("variables", checkbox.value));
    params.set("start", start);
    params.set("end", end);

    setStatus("Loading data…");
    let body;
    try {
      const response = await fetch(
        `${BASE_PATH}/datasets/${encodeURIComponent(currentDatasetId)}/data?${params.toString()}`
      );
      if (!response.ok) {
        setStatus("Could not load data for the selected range.");
        return;
      }
      body = await response.json();
    } catch (err) {
      setStatus("Could not load data for the selected range.");
      return;
    }

    renderChart(body, checked);
    setStatus("");
  }

  function resolveDateRange() {
    const startInput = document.getElementById("viz-start");
    const endInput = document.getElementById("viz-end");
    const now = new Date();
    const defaultStart = new Date(now.getTime() - DEFAULT_LOOKBACK_MS);

    // A blank field falls back to the bounded default, not "full record"
    // (unlike the dataset panel's own download popover) — see the
    // DEFAULT_LOOKBACK_MS comment above for why.
    const start = startInput.value || toDateInputValue(defaultStart);
    const end = endInput.value || toDateInputValue(now);
    return { start, end };
  }

  function renderChart(body, checkedCheckboxes) {
    const canvas = document.getElementById("viz-chart");
    if (!canvas) return;

    const times = body.time || [];
    const axisIdByUnits = new Map();
    const scales = { x: { type: "category", ticks: { autoSkip: true } } };
    const datasets = [];
    let colorIndex = 0;

    checkedCheckboxes.forEach((checkbox) => {
      const name = checkbox.value;
      const units = checkbox.dataset.units || "";

      if (!axisIdByUnits.has(units)) {
        const axisId = axisIdByUnits.size === 0 ? "y" : `y${axisIdByUnits.size}`;
        axisIdByUnits.set(units, axisId);
        scales[axisId] = {
          type: "linear",
          position: axisIdByUnits.size % 2 === 1 ? "left" : "right",
          title: { display: !!units, text: units },
        };
      }
      const axisId = axisIdByUnits.get(units);

      // core/export.py::to_wide_dataframe explodes an extra_dimension
      // variable into "<name>_<segment>" columns (e.g. a multi-height
      // air_temperature -> air_temperature_2m, air_temperature_10m) — the
      // response's keys aren't guaranteed to equal the requested variable
      // name 1:1, so match by prefix rather than a direct body[name] lookup,
      // or an exploded variable's data silently never renders.
      const matchedKeys = Object.keys(body).filter(
        (key) => key !== "time" && (key === name || key.startsWith(name + "_"))
      );

      matchedKeys.forEach((key) => {
        const color = AXIS_COLORS[colorIndex % AXIS_COLORS.length];
        colorIndex += 1;
        datasets.push({
          label: key,
          data: body[key],
          borderColor: color,
          backgroundColor: color,
          yAxisID: axisId,
          spanGaps: false, // a real gap in the record is shown as a gap, never interpolated
          pointRadius: 0,
          borderWidth: 1.5,
        });
      });
    });

    clearChart();
    chartInstance = new Chart(canvas, {
      type: "line",
      data: { labels: times, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: scales,
        plugins: { legend: { display: true } },
      },
    });
  }

  function clearChart() {
    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }
  }

  function setStatus(message) {
    const status = document.getElementById("viz-status");
    if (status) status.textContent = message;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
