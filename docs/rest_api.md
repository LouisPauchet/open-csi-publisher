# REST API

All endpoints below are implemented in `api/routers/datasets_api.py` and
`api/routers/dataset_detail.py`. None of them require authentication for **public**
datasets. A **restricted** dataset 404s identically to an unknown id for an
unauthenticated caller — see `api/access.py` — since there's currently no login flow
(see `architecture.md`'s "what's built vs. planned"), restricted datasets are
unreachable through any of these endpoints today.

## `GET /datasets`

Lists visible datasets. Query params (all optional, all combinable):

| Param | Meaning |
|---|---|
| `q` | Case-insensitive substring match against title/institution/id/metadata values |
| `platform_type` | `fixed` or `mobile`, exact match |
| `standard_name` | Repeatable — dataset must have **all** requested variables |
| `meta.<key>` | Repeatable — substring match against `metadata[key]` (open-ended: any key present in any dataset's metadata works, including `department`/`project`/etc.) |

Response: `{"datasets": [...], "total": N}`. Each dataset summary includes `position`
(resolved `{lat, lon, elevation}` for fixed platforms from config; always `null` for
mobile platforms — see below).

## `GET /datasets/{id}`

Calls `build_dataset()` (the full dataset, like `/data` and the downloads do — more work
than a config-only lookup, but it's what lets `metadata` below carry everything
`build_dataset()` computes, not just the static config-declared fields). Response
includes: `title`, `platform_type`, `access`, the variable list
(name/standard_name/units/dtype), the raw deployments list, `time_coverage` (`{start,
end}`, or `null` if the dataset has no data yet), and `metadata` — every config-declared
metadata field (including arbitrary extra keys like `department`) *plus* everything
computed at build time:

| Key(s) | Meaning |
|---|---|
| `unis_id` | This portal's internal dataset id — deliberately not `id`; see below. |
| `processing_software_version`, `config_hash`, `config_version_timestamp`, `history` | Provenance — which app/config version produced this. |
| `geospatial_lat_min`/`_max`, `geospatial_lon_min`/`_max` | ACDD-style bounding box, computed from the actual data (fixed stations: constant; mobile: real track extent). Omitted if latitude/longitude isn't present. |
| `time_coverage_start`/`_end` | ISO 8601 UTC, computed from the actual `time` values (not the file index) — see `core/builder.py::_build_coverage_attrs`. |

**Why `unis_id`, not `id`**: ACDD reserves `id` (+ `naming_authority`, a settable
`MetadataSpec` field) for whichever downstream system formally publishes/archives this
data and assigns its own citable identifier. This portal isn't that publisher, so its
own internal slug uses a namespaced attribute instead of claiming `id` for itself. The
same convention applies to the NetCDF/OPeNDAP/CSV global attributes below.

## `GET /datasets/{id}/deployments`

The raw `deployments` list from config — no data I/O. For `fixed` datasets: position
windows (`lat`/`lon`/`elevation`). For `mobile` datasets: platform-identity windows
(`platform_name`) — position itself is **not** here, it's data (see below).

## `GET /datasets/{id}/data`

Calls `build_dataset()` directly. Query params: `start`, `end` (ISO datetime, both
optional — omit for the full available range), `variables` (repeatable canonical
names, omit for all configured variables), `format` (`json` default, or `csv`).

`format=json` shape: `{"time": [...], "<variable>": [...], ...}` — one array per
variable, index-aligned with `time`. Missing values are `null`, not `NaN` (real sensor
data has gaps; standard JSON has no `NaN` literal, so this endpoint substitutes `null`
after converting from `xarray`/`pandas`, since assigning `None` directly into a
`float64` column gets silently cast back to `NaN` by pandas — the substitution has to
happen after `to_dict()`, at the plain-Python-list level). For an `extra_dimension`
variable (e.g. a
height-stacked group), the response naturally broadcasts onto every `(time, <dim>)`
combination via `xarray`'s own `to_dataframe()`, so plain `(time,)` variables appear
duplicated once per dimension value in that case — a standard `xarray`/`pandas`
flattening, not a hand-rolled scheme.

**This is how the listing page's map gets a mobile dataset's position** — there's no
separate "position" endpoint; the map's frontend just requests
`/datasets/{id}/data?variables=latitude&variables=longitude&start=<recent>` and uses
the last point as "current position" and the full series as a recent track.

## `GET /datasets/{id}/download.nc` and `/download.csv`

Same as `/data` but no `variables` restriction (full dataset) and streamed as a file
download (`Content-Disposition: attachment`). `.nc` uses `engine="h5netcdf"` for clean
variable-length string support (status/flag columns) without manual char-array
encoding.
