# Environmental Data Portal — Implementation Plan

## 1. Purpose

Build a system that ingests environmental monitoring data (starting with Campbell
Scientific LoggerNet `.dat` files, extensible to other source types) and exposes it via:

- **OPeNDAP** (public datasets only)
- **NetCDF / CSV download** (public + restricted datasets)
- **REST API** (dataset listing, metadata, station map, data queries)
- **Grafana-compatible interface** (live visualization)
- **Protected publish endpoint** for the downstream data center to pull the latest
  complete monthly NetCDF per dataset, on demand (no scheduled job)

Core design principle: **no NetCDF is stored as the primary data layer**. Everything
served live (OPeNDAP, REST, ad-hoc downloads, and the monthly publish endpoint) is
built on the fly from raw source files/records, using one shared core. Monthly files
are generated on request (when listed/pulled), not pre-generated on a schedule, and
are treated as immutable/versioned once produced.

---

## 2. High-Level Architecture

```
                     ┌─────────────────────────────┐
                     │   sources.yaml (top-level)   │
                     │  lists available data sources│
                     └──────────────┬──────────────┘
                                    │
                 ┌──────────────────┴──────────────────┐
                 │                                      │
         ┌───────▼────────┐                    ┌────────▼────────┐
         │ Config Provider │                    │  Data Provider  │
         │  (per source)   │                    │  (per source)   │
         │ folder / db /...│                    │ files / db /... │
         └───────┬────────┘                    └────────┬────────┘
                 │                                      │
                 └──────────────────┬───────────────────┘
                                    │
                          ┌─────────▼──────────┐
                          │   Dataset object    │
                          │ (normalized, source- │
                          │  type agnostic)      │
                          └─────────┬──────────┘
                                    │
        ┌───────────────┬──────────┼───────────────┬────────────────┐
        │               │          │               │                │
  ┌─────▼─────┐  ┌──────▼─────┐ ┌──▼───────┐ ┌─────▼──────┐  ┌──────▼──────┐
  │  PyDAP     │  │  REST API  │ │ Download │ │  Grafana   │  │  Publish    │
  │  OPeNDAP   │  │  (+ map)   │ │ endpoint │ │  bridge    │  │  endpoint   │
  │  handler   │  │            │ │(nc/csv)  │ │            │  │ (API-key    │
  │(public only)│  │            │ │          │ │            │  │  protected) │
  └────────────┘  └────────────┘ └──────────┘ └────────────┘  └──────┬──────┘
                                                                       │
                                                               ┌───────▼───────┐
                                                               │ Data center   │
                                                               │ pulls latest  │
                                                               │ complete month│
                                                               └───────────────┘
```

All five consumers at the bottom call into the **same core library** — they never
re-implement data assembly independently.

---

## 3. Storage & Mount Layout

| Location | Access | Contents |
|---|---|---|
| Data mount (S3-backed, per source) | **read-only** for the server | Raw source files (e.g. LoggerNet `.dat`), and `__config__/` folder with per-dataset JSON configs (for file-based sources) |
| Server state store (DB, e.g. Postgres/SQLite + local volume) | read-write | Config snapshots & version history, file/data index (manifest), processing logs, cache, generated monthly NetCDF cache |

The server must **never** write to the data mount. All server-owned state — including
config version history and generated monthly files — lives in a separate, dedicated
state store. There is no rsync push anymore: the data center pulls files via the
protected publish endpoint (§11) instead.

---

## 4. Configuration Layers

### 4.1 Top-level sources file (`sources.yaml`)

Server-managed deployment config, read at startup (and periodically refreshed).
Lists every available data source and how to reach it.

```yaml
sources:
  - id: station_network_a
    type: loggernet
    config_provider: folder
    config_location: s3://bucket-a/__config__/
    data_location: s3://bucket-a/

  - id: future_source
    type: some_other_type
    config_provider: database
    connection: <connection details>
```

### 4.2 Per-dataset config (normalized envelope)

Regardless of source type, every dataset config resolves into the same shape:

```json
{
  "id": "station_001",
  "source_type": "loggernet",
  "access": "public",
  "source_config": {
    "file_pattern": "CR1000_Table1_*.dat",
    "timestamp_column": "TIMESTAMP",
    "table_name": "Table1"
  },
  "variables": [
    {"raw_name": "AirTC_Avg", "old_names": ["AirTemp_Avg", "TAir"],
     "standard_name": "air_temperature", "units": "degC"},
    {
      "standard_name": "air_temperature",
      "units": "degC",
      "extra_dimension": {"name": "height", "units": "m"},
      "members": [
        {"raw_name": "AirTC_2m_Avg", "dimension_value": 2},
        {"raw_name": "AirTC_10m_Avg", "dimension_value": 10},
        {"raw_name": "AirTC_30m_Avg", "dimension_value": 30}
      ]
    }
  ],
  "platform_type": "fixed",
  "deployments": [
    {"start": "2019-05-01T00:00:00Z", "end": "2022-03-14T00:00:00Z",
     "lat": 46.123, "lon": 6.789, "elevation": 410},
    {"start": "2022-03-14T00:00:00Z", "end": null,
     "lat": 46.130, "lon": 6.791, "elevation": 415}
  ],
  "metadata": {
    "title": "...", "institution": "...", "license": "...",
    "naming_authority": "...", "standard_name_vocabulary": "CF-1.10"
  },
  "output": {
    "file_naming": "{station}_{table}_{yyyy}-{mm}.nc",
    "publish": true
  }
}
```

Only `source_config` varies per source type; every other section is shared.

**Variable name aliasing:** a raw column's name in the source files can change over
time (sensor swap, logger reprogramming, etc.). Each variable entry carries an
`old_names` list so the data provider can map any historical header name to the same
standard variable, rather than treating a renamed column as a new/unmapped one.

**Multi-column variables with an extra dimension:** some stations report the same
physical quantity at several levels/positions as separate raw columns (e.g.
temperature at 2m/10m/30m on a weather mast). Instead of exposing these as N
unrelated variables, a variable entry can define `extra_dimension` (name + units,
e.g. `height`/`m`) plus a `members` list mapping each raw column to a value along
that dimension. The data provider/builder combines these columns into a single
output variable with the extra dimension as a coordinate — matching how this is
normally represented in CF-compliant NetCDF (e.g. a `height` dimension alongside
`time`), rather than as flat, independently-named variables.

**Fixed vs. moving platforms (`platform_type: fixed | mobile`):**
- `fixed` (the default case so far): `deployments` is a list of static position
  periods, as above — position is metadata, resolved per request/at publish time.
- `mobile` (e.g. a station mounted on a boat with GPS tracking): `deployments`
  instead describes the *platform* itself (e.g. which vessel, instrument
  configuration, start/end of that mounting), and position is **not** a deployment
  field at all — it's treated as an ordinary time-varying variable read directly
  from the data (a GPS lat/lon/elevation column), the same way temperature or
  humidity would be. The core builder and NetCDF output need to handle
  coordinate variables that vary per-timestep for these datasets, rather than
  assuming one static lat/lon per deployment period.

### 4.3 Config provider interface

```python
class ConfigProvider(ABC):
    def list_dataset_ids(self) -> list[str]: ...
    def load_config(self, dataset_id: str) -> dict: ...
    def config_hash(self, dataset_id: str) -> str: ...
```

Implementations: `FolderConfigProvider` (scans `__config__/*.json` on a mount),
`DatabaseConfigProvider` (queries a source's own DB), etc.

### 4.4 Config versioning (applies to all source types)

- **Lazy, not polled**: triggered on dataset access (REST/OPeNDAP/download call, or
  a publish-endpoint request) — not a background watcher.
- On access: compute `config_hash()`, compare to last-known hash in the state store.
- If changed: snapshot the new config content + `{dataset_id, hash, timestamp}` into
  the state store. This becomes "current."
- No retroactive rewriting: generated monthly files always used whatever config
  version was current at the time they were built, and are never regenerated when
  the config later changes.
- Known edge case (a past published file turns out to reflect a wrong deployment
  position, etc.) is handled manually — no formal correction/erratum workflow needed.

---

## 5. Data Providers

### 5.1 Interface

```python
class DataProvider(ABC):
    def get_file_index(self, source_config: dict) -> list[FileRecord]: ...
    def read_range(self, source_config: dict, start, end, variables=None) -> StandardReading: ...
```

`StandardReading` is the normalized in-memory representation (e.g. a tidy
`{timestamp, variable: value, ...}` table or an xarray-like structure) that every
downstream consumer (builder, publisher, REST) operates on — independent of source type.

### 5.2 LoggerNet data provider (first implementation)

- Discovers files via `file_pattern` glob on the mounted share.
- Parses `.dat` (CSV) files, using `timestamp_column` and `table_name` from config.
- Maintains the **file/data index** (see §6) to avoid re-parsing unchanged files.

---

## 6. File/Data Index (Manifest)

Per dataset, tracks which files cover which time ranges, stored in the state store
(not the read-only data mount):

```json
{
  "dataset_id": "station_001",
  "files": [
    {"file": "CR1000_Table1_2023_01.dat", "size": 48213, "start": "...", "end": "...",
     "variables": ["AirTC_Avg", "RH"], "status": "closed"},
    {"file": "CR1000_Table1_2024_06.dat", "size": 91234, "start": "...", "end": "...",
     "variables": ["AirTC_Avg", "RH"], "status": "active"}
  ]
}
```

**Refresh logic (lazy, triggered by access, same event as config versioning check):**
1. List files matching the pattern on the mount.
2. New filenames (not yet indexed) → parse once, extract time range + variables,
   mark `status: active` initially.
3. For files already indexed with `status: active`: `stat()` the file size.
   - Size unchanged since last check → mark `status: closed`, cache permanently,
     never re-check again.
   - Size changed → re-parse, refresh time range, keep `status: active`.
4. Files with `status: closed` are never touched again.
5. Belt-and-suspenders: always re-check the most-recent-by-name file regardless of
   its recorded status, in case a status transition was missed.

**Consistency caveat:** verify the actual mount type's (s3fs/goofys/etc.) read-after-
write consistency behavior before relying on `stat()` timing for correctness.

---

## 7. Core Builder (shared by OPeNDAP, REST, downloads, and the publish endpoint)

Single function/class, roughly:

```python
def build_dataset(dataset_id: str, start=None, end=None, variables=None) -> StandardReading:
    config = config_provider.load_config(dataset_id)          # + lazy version check
    index = get_or_refresh_index(dataset_id)                   # lazy refresh
    files = select_files_covering(index, start, end)
    data = data_provider.read_range(config["source_config"], start, end, variables)
    data = apply_deployment_metadata(data, config["deployments"])  # position at time T
    return data
```

- `apply_deployment_metadata` behavior depends on `platform_type`:
  - `fixed`: resolves station position (and any other deployment-varying attribute)
    for the requested time range from the config's `deployments` list.
  - `mobile`: position comes straight from the data itself (a GPS variable in
    `StandardReading`, per §4.2) — this step instead attaches which platform/vessel
    was in use for the period, from `deployments`, without touching position.
  - In both cases, **live** queries always reflect current-best config, while the
    **publish endpoint** bakes deployment values (and, for `fixed` platforms,
    resolved position) in permanently at write time.

---

## 8. OPeNDAP Layer (PyDAP)

- Custom PyDAP handler that, per request:
  1. Parses the requested dataset id + constraint expression (time range, variables).
  2. Calls the core builder.
  3. Constructs an in-memory `pydap.model.DatasetType` from the `StandardReading`.
- **Public datasets only** — restricted (`access: restricted`) datasets are never
  registered with / served by this handler at all.
- Add a short TTL in-memory cache (e.g. per dataset+timerange) in front of the
  builder to absorb repeated Grafana/OPeNDAP polling without re-parsing files or
  re-hitting the mount on every request.

---

## 9. REST API

| Endpoint | Notes |
|---|---|
| `GET /datasets` | Public datasets only for anonymous callers. Restricted datasets fully omitted (not just download-blocked) unless caller has a valid session. Includes current resolved position per dataset → feeds the map view. |
| `GET /datasets/{id}` | Metadata, variables, deployment history, time coverage (from index). |
| `GET /datasets/{id}/deployments` | Full position history (for a station-track map view). |
| `GET /datasets/{id}/data?start=&end=&variables=&format=json\|csv` | Calls core builder. |
| `GET /datasets/{id}/download.nc` / `download.csv` | Full-file download. Restricted datasets require valid Entra ID session (browser-based). |

Grafana can consume this API directly (JSON API / Infinity datasource plugin),
reusing the same endpoints — no separate Grafana-specific code path needed.

---

## 10. Access Control

- Per-dataset `access: public | restricted` flag in config.
- **Public**: visible in listings, servable via OPeNDAP, REST, and download, to anyone.
- **Restricted**:
  - Never exposed via OPeNDAP (no DAP access at all).
  - Invisible in `/datasets` listings to anonymous/non-authenticated callers —
    not merely download-blocked.
  - Download + REST data endpoints require a valid Microsoft 365 (Entra ID) session
    via standard OIDC browser login (session cookie) — no token/API-key scheme
    needed, since restricted access is download-only (no non-browser DAP clients
    to support).
- Grafana access to restricted datasets, if ever needed, relies on Grafana's own
  native Azure AD/Entra ID auth integration.

---

## 11. Publish Endpoint (Data Center Access — Replaces Cron Job)

Instead of a scheduled job pushing files to an rsync share, the data center pulls
on its own schedule via a small, separately-authenticated API:

| Endpoint | Notes |
|---|---|
| `GET /publish/datasets` | Lists publishable datasets (`output.publish: true`), each with the latest *complete* month available and a download URL for it. |
| `GET /publish/{dataset_id}/{yyyy-mm}` | Returns (generating on demand if not already cached) the NetCDF file for that month. |

**"Complete month" logic:** a month is only listed once it has fully closed —
i.e. the current date has moved past it — combined with the active-file detection
from §6, so a month isn't considered complete while its underlying `.dat` file
could still be appended to.

**Generation is on-demand, not scheduled:** the first request for a given
dataset+month calls the same core builder (§7) fixed to that month's window,
writes the NetCDF, and caches it (in the state store / a temp directory) so
subsequent pulls of the same month are served from cache rather than rebuilt.
Deployment values are resolved and baked in permanently at generation time (same
`fixed`/`mobile` handling as before), and provenance attributes
(`processing_software_version`, `config_hash`, `config_version_timestamp`) are
still embedded.

**File naming** from `output.file_naming` in config, e.g. `{station}_{table}_{yyyy}-{mm}.nc`,
used as the generated file's name and in the returned download URL.

**Auth:** protected by a static API key, not the Entra ID session flow used
elsewhere. Valid keys are supplied to the server via an **environment variable**
(a list, not stored in the DB/config) and checked on every request to this
endpoint set (e.g. `Authorization: Bearer <key>`). This is a separate, simpler
mechanism intended for a small number of trusted server-to-server consumers (the
data center), not end users — no session, no redirect flow, no per-user identity.

**No retroactive rewriting still applies:** once a given month has been generated
and cached, it isn't silently regenerated if the config changes later —
regenerating (if ever needed) would be a deliberate, manual action.

---

## 12. State Store Schema (server-owned, not on the data mount)

Minimum tables/collections:

- `config_versions`: `{dataset_id, hash, timestamp, content}`
- `file_index`: `{dataset_id, file, size, start, end, variables, status}`
- `publish_log`: `{dataset_id, period, config_hash, software_version, generated_at, cached_file_path}`
- `api_keys` (or env-var only, no table needed): valid publish-endpoint keys are
  read from an environment variable at startup, not stored in the DB
- (optional) request/response cache for the OPeNDAP/REST TTL cache layer

---

## 13. Extensibility: Additional Source Types

Two independent plugin points — a new source type can mix and match:

1. **Config provider** — where/how dataset configs for this source are discovered
   (folder scan, DB query, API call, ...).
2. **Data provider** — how actual readings are fetched and how "new/active" data
   is detected (LoggerNet: file size heuristic; a DB-backed source might use a
   `last_modified` column or change-log table instead).

Both must normalize into the same `Dataset` / `StandardReading` shapes so every
consumer above (§7–§11) remains completely source-type-agnostic.

---

## 14. Suggested Build Order

1. **Core data model**: `Dataset` object, `StandardReading` shape, config envelope schema.
2. **LoggerNet data provider**: `.dat` parsing, file discovery, active-file detection.
3. **Folder config provider**: load/validate JSON configs from `__config__/`.
4. **File/data index**: build + lazy refresh logic, backed by the state store.
5. **Config versioning**: lazy hash-check + snapshot, backed by the state store.
6. **Core builder**: ties config + index + data provider + deployment resolution together.
7. **REST API**: dataset listing, metadata, data query, download endpoints (no auth yet).
8. **Access control**: public/restricted flag, Entra ID session auth for downloads/REST.
9. **OPeNDAP handler**: PyDAP custom handler wrapping the core builder (public only).
10. **Map/station view**: front-end consuming `/datasets` (+ `/deployments`).
11. **Publish endpoint**: latest-complete-month listing, on-demand NetCDF
    generation + cache, API-key auth via env var.
12. **Grafana integration**: verify JSON API datasource against the REST API.
13. **Second source type** (even a minimal stub) to stress-test the plugin interfaces
    before committing to their shape long-term.

---

## 15. Config-Creation CLI

A helper CLI so users don't hand-write dataset JSON configs from scratch. Scoped to
the LoggerNet source type first, but should be structured so a new source type can
plug in its own "scan + suggest" logic later (same plugin-interface principle as §13).

**Suggested flow:**

1. **Locate files**: prompt for a starting path/glob, show matching files found on
   the mount, let the user iterate on the pattern until it matches the intended set
   (and only that set).
2. **Scan header**: read the header row(s) of a sample file (LoggerNet `.dat` files
   typically carry column names + units in the header) and list detected columns.
3. **Variable mapping assist**: for each detected raw column name, suggest a
   `standard_name` / `units` pair — e.g. fuzzy-match against a small built-in table
   of common LoggerNet variable names (`AirTC_Avg` → `air_temperature`, `degC`) and
   the CF standard names table, falling back to "unmapped, please specify" for
   anything not recognized. User confirms or overrides each suggestion.
3b. Detect units already present in the file header, where LoggerNet provides them,
   and use those as the default rather than guessing.
4. **Deployment prompt**: ask for at least one deployment entry (start date,
   position); explain that more can be added later for station moves.
5. **Metadata defaults**: pre-fill `metadata` fields with sensible defaults (e.g.
   `standard_name_vocabulary: CF-1.10`, institution/license from a project-wide
   default if configured) and let the user override.
6. **Access flag**: prompt public vs. restricted.
7. **Validate & write**: assemble the full config envelope (§4.2), validate it
   against the schema, show a diff/preview, then write to `__config__/`.

**Runs on the data collection server, not the app/serving server:** the CLI is
installed and run where the operator has write access to the mount (the data
collection server), separate entirely from the read-only app server (§3). No
special credential handling is needed on the app-server side as a result — the
read-only constraint there remains absolute; only the CLI's own host ever writes
to `__config__/`.

**Implementation notes:**
- Reuse the LoggerNet data provider's header-parsing logic (§5.2) rather than
  duplicating a separate parser inside the CLI.
- The variable name/unit suggestion table is a good candidate for its own small,
  editable reference file (e.g. `known_variables.yaml`) rather than hardcoded
  mappings, so it can grow as new sensor types are encountered.
- Consider a non-interactive mode (flags/answers file) for scripted/bulk config
  creation, in addition to the interactive prompt flow.
- **Re-running the CLI on an existing dataset** (e.g. after a sensor swap changes a
  header name) should detect columns no longer matching any `raw_name` but matching
  an entry's `old_names`, and offer to just confirm the mapping rather than treating
  it as a brand-new unmapped variable. For a genuinely new/unrecognized column, offer
  to append it to the existing config rather than starting over.
- For `platform_type: mobile` datasets, the CLI should detect likely GPS/position
  columns during header scanning and prompt the user to confirm they should be
  treated as ordinary variables (not deployment fields), pre-selecting standard
  names like `latitude`/`longitude` for them.
- The CLI should also flag likely multi-level column groups during header scanning
  (e.g. columns sharing a common prefix/suffix pattern like `AirTC_2m_Avg`,
  `AirTC_10m_Avg`) and offer to combine them into one `extra_dimension` variable
  entry, pre-filling the dimension values parsed from the column names, rather than
  requiring the user to construct that grouping by hand.

---

## 16. Open Questions / Deferred Decisions

- Exact mount technology (s3fs, goofys, etc.) and its read-after-write consistency —
  needs empirical verification before relying on lazy `stat()`-based checks.
- Whether Grafana will ever need access to restricted datasets (affects whether
  Grafana's own Entra ID integration needs to be wired up at all).
- Formal correction/erratum path for published files — currently deferred, handled
  manually on a case-by-case basis.
