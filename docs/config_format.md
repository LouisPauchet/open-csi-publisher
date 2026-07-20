# Dataset config format

A dataset config is a JSON file, validated against `DatasetConfig`
(`src/open_csi_publisher/core/config_schema.py`). The three files in
`sample_configs/` are real, worked examples against real UNIS station data — this page
explains the shape; read those files alongside it for concrete values.

| File | What it demonstrates |
|---|---|
| `sample_configs/isfjord_radio_solar_park_measurements3.json` | Fixed station, an `extra_dimension` variable group, a `.dat.backup`-style archived file |
| `sample_configs/kapp_thordsen_10minute.json` | Fixed station with a `_Historical`-style archived file, including a real time gap and a column added after the archived file was written |
| `sample_configs/hanna_resvoll_10min.json` | Mobile (boat-mounted) station — position comes from the data, not from `deployments` |

## Top-level fields

- `id` — must match the filename (`<id>.json`); this is how `FolderConfigProvider`
  resolves a dataset id to a file, without needing to parse every file's contents just
  to list what's available.
- `source_type` — `"loggernet"` or `"generic_csv"` (the latter is a minimal second
  source type that exists to prove the plugin boundary works, not a real deployed UNIS
  source — see `tests/fixtures/generic_csv/` for its shape; every real config in
  `sample_configs/` is `"loggernet"`).
- `access` — `"public"` or `"restricted"`. Restricted datasets are invisible in listings
  and unreachable through every other endpoint (detail, data, downloads, OPeNDAP) for
  anonymous callers (see `api/access.py`).
- `source_config` — source-type-specific; its shape is validated against whichever
  schema matches `source_type` (a discriminated union — see `architecture.md`).
- `variables` — which raw columns become which output variables (see below).
- `platform_type` — `"fixed"` or `"mobile"` (see below).
- `deployments` — meaning depends on `platform_type`.
- `metadata` — global attributes; `title` is required, everything else is optional.
  **Arbitrary extra keys are allowed** (e.g. `department`, `project`) and are exactly
  what the dataset listing page's metadata filter searches over — this is deliberate,
  not a schema gap. `description` is one such key with a special role in the UI: the
  listing table shows it as its own column (instead of dumping every metadata field
  into the row — that full set is still available in the detail panel once a dataset is
  selected), so it's worth setting to a short, human-readable summary of the station.
- `output.file_naming` — filename template for generated monthly files, used by the
  [publish endpoint](publish_endpoint.md) (e.g. `{station}_{table}_{yyyy}-{mm}.nc`).
- `output.publish` — whether this dataset is exposed via the publish endpoint at all.

## `source_config` (LoggerNet)

```json
{
  "file_pattern": "StationFolder/StationName_Table.dat",
  "timestamp_column": "TIMESTAMP",
  "table_name": "Table_10minute",
  "historical_suffix": "_Historical"
}
```

**`file_pattern` must match the live file only, ending in a literal `.dat`.** Do not try
to write one glob that also catches the archived file — the provider derives the
archived-file patterns (`_Historical.dat` and `.dat.backup*`) from `file_pattern`
itself. This matters because LoggerNet table names can be prefixes of each other (e.g.
`Min`, `Min10`, `Min60`); a pattern like `*_Min*` would incorrectly also match `Min10`'s
files.

## `variables`

Each entry is **either** a single raw column:

```json
{"raw_name": "AirT_C", "standard_name": "air_temperature", "units": "degC"}
```

**or** a group of raw columns stacked along a new dimension:

```json
{
  "extra_dimension": {"name": "height", "units": "m"},
  "members": [
    {"raw_name": "AirTC_2m_Avg", "dimension_value": 2},
    {"raw_name": "AirTC_10m_Avg", "dimension_value": 10}
  ],
  "standard_name": "air_temperature",
  "units": "degC"
}
```

Not every raw column needs an entry — anything not listed is simply dropped from the
output (see `hanna_resvoll_10min.json`'s `GPS_location`, deliberately left unmapped).

- The output variable's name is `standard_name` if set, else `raw_name`.
- `old_names` lists earlier raw column names for the same variable (e.g. after a sensor
  swap). If a merged time series has both the old and new column populated for disjoint
  time ranges, they're coalesced into one series, not just one-or-the-other.
- `dtype: "string"` for non-physical columns (status/flag strings like
  `MetSENS_Status`) — no `standard_name`/`units` needed for these.

## `platform_type` and `deployments`

**`fixed`** — `deployments` is a list of static position periods:

```json
{"start": "2020-01-01T00:00:00Z", "end": null, "lat": 78.06, "lon": 13.63, "elevation": 10}
```

Only the *last* deployment may have `end: null` (open-ended); earlier ones must have an
explicit `end`, and windows must not overlap.

**`mobile`** — `deployments` describes the *platform*, not a position:

```json
{"start": "2026-05-18T00:00:00Z", "end": null, "platform_name": "Example Boat"}
```

Position instead comes from the data itself: the config must map raw columns to
`standard_name: "latitude"` and `"longitude"` in `variables`, exactly like any other
measured quantity.

Deployment `start`/`end` can be written with or without a UTC offset (`Z` suffix) — they
are normalized to naive UTC internally, matching the raw LoggerNet timestamps, which
carry no timezone information at all.
