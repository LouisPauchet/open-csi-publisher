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
  // The most recent successful /data response, so adjusting an axis range
  // (see applyAxisRangeOverride) can just re-render, not refetch.
  let lastBody = null;
  let lastCheckedCheckboxes = null;
  // Chart.js auto-scales each axis from the data, which one sensor fill/
  // error-value outlier can squash flat — keyed by units string (the same
  // key axes are grouped by) rather than dataset id, so a manually-set
  // range survives re-renders and switching between variables that share
  // the same units.
  const axisRangeOverrides = {};

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

    lastBody = body;
    lastCheckedCheckboxes = checked;
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
    const scales = {
      x: {
        type: "category",
        ticks: {
          autoSkip: true,
          maxTicksLimit: 12, // a hard cap regardless of how many points are plotted
          maxRotation: 45,
          minRotation: 0,
          // For a category scale, Chart.js's tick `value` is the label's
          // index into `data.labels`, not the label text — resolve back to
          // the actual ISO string via the scale's own getLabelForValue,
          // then shorten it (the raw "2026-07-10T00:18:10" strings this
          // page fetches are unreadably dense once rotated).
          callback: function (value) {
            return formatTimeLabel(this.getLabelForValue(value));
          },
        },
      },
    };
    const datasets = [];
    let colorIndex = 0;

    checkedCheckboxes.forEach((checkbox) => {
      const name = checkbox.value;
      const units = checkbox.dataset.units || "";

      if (!axisIdByUnits.has(units)) {
        const axisId = axisIdByUnits.size === 0 ? "y" : `y${axisIdByUnits.size}`;
        axisIdByUnits.set(units, axisId);
        const axisConfig = {
          type: "linear",
          position: axisIdByUnits.size % 2 === 1 ? "left" : "right",
          title: { display: !!units, text: units },
        };
        const override = axisRangeOverrides[units];
        if (override && typeof override.min === "number") axisConfig.min = override.min;
        if (override && typeof override.max === "number") axisConfig.max = override.max;
        scales[axisId] = axisConfig;
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

    renderAxisRangeControls(axisIdByUnits);

    destroyChart();
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

  // One "<units> axis: min [__] max [__]" control group per distinct units
  // among the currently checked variables. Rebuilt on every renderChart()
  // call, pre-filled from axisRangeOverrides so an in-progress edit survives
  // a variable/date-range change that triggers a re-render.
  function renderAxisRangeControls(axisIdByUnits) {
    const container = document.getElementById("viz-axis-ranges");
    if (!container) return;

    if (axisIdByUnits.size === 0) {
      container.innerHTML = "";
      return;
    }

    container.innerHTML = Array.from(axisIdByUnits.keys())
      .map((units) => {
        const override = axisRangeOverrides[units] || {};
        const minValue = typeof override.min === "number" ? override.min : "";
        const maxValue = typeof override.max === "number" ? override.max : "";
        const label = units ? escapeHtml(units) : "no units";
        return (
          `<label class="viz-axis-range-group">` +
          `${label} axis:` +
          ` <input type="number" class="viz-axis-min" data-units="${escapeHtml(units)}" placeholder="min" step="any" value="${minValue}">` +
          ` – ` +
          `<input type="number" class="viz-axis-max" data-units="${escapeHtml(units)}" placeholder="max" step="any" value="${maxValue}">` +
          `</label>`
        );
      })
      .join("");

    container.querySelectorAll(".viz-axis-min").forEach((input) => {
      input.addEventListener("change", () => applyAxisRangeOverride(input.dataset.units, "min", input.value));
    });
    container.querySelectorAll(".viz-axis-max").forEach((input) => {
      input.addEventListener("change", () => applyAxisRangeOverride(input.dataset.units, "max", input.value));
    });
  }

  function applyAxisRangeOverride(units, field, rawValue) {
    if (!axisRangeOverrides[units]) axisRangeOverrides[units] = {};
    const parsed = rawValue === "" ? null : parseFloat(rawValue);
    axisRangeOverrides[units][field] = Number.isNaN(parsed) ? null : parsed;

    // Re-render from the already-fetched data — no need to hit the network
    // again just because the displayed range changed.
    if (lastBody && lastCheckedCheckboxes) {
      renderChart(lastBody, lastCheckedCheckboxes);
    }
  }

  // Short, fixed-width local-ish label ("07-10 00:18") instead of a full ISO
  // timestamp — this page doesn't need calendar-correct locale formatting,
  // just something compact enough not to overwhelm the axis once rotated.
  function formatTimeLabel(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function clearChart() {
    destroyChart();
    const rangesContainer = document.getElementById("viz-axis-ranges");
    if (rangesContainer) rangesContainer.innerHTML = "";
  }

  function destroyChart() {
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
