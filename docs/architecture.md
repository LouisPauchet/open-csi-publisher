# Architecture

For the overall system design — why it's built this way, access control, and the
extensibility story for additional source types — see
[`implementation_plan.md`](../implementation_plan.md) at the repo root. This page is
just a map from that design onto the code that currently exists, so you know where to
look.

## Module map

```
src/open_csi_publisher/
├── settings.py              Env-var configuration (pydantic-settings)
├── sources.py                sources.yaml -> providers, cross-source dataset enumeration
├── core/
│   ├── config_schema.py      The dataset config envelope (Pydantic); discriminated
│   │                         source_config union (loggernet | generic_csv)
│   ├── config_versioning.py  Lazy hash-check + snapshot (get_versioned_config)
│   ├── variable_mapping.py   Raw columns -> canonical output variables
│   ├── deployment.py         Fixed position / mobile platform resolution
│   ├── search_index.py       Config -> flattened listing/search document
│   ├── publish.py            Month-completeness logic for the publish endpoint
│   ├── models.py             FileRecord (in-memory file-index entry)
│   └── builder.py            build_dataset() / resolve_time_coverage() — the shared pipeline
├── providers/
│   ├── base.py                ConfigProvider / DataProvider ABCs
│   ├── config/folder.py       FolderConfigProvider (scans *.json in a folder; source-type-agnostic)
│   └── data/
│       ├── loggernet/
│       │   ├── toa5.py         TOA5 .dat header + body parsing
│       │   ├── fileset.py      Live/archived file classification + reconciliation
│       │   └── provider.py     LoggerNetDataProvider (get_file_index / read_range)
│       └── generic_csv/
│           └── provider.py     GenericCsvDataProvider — second source type, mtime-based
├── index/service.py          Lazy file-index refresh orchestration
├── state/                    SQLAlchemy models + repository (config_versions, file_index, publish_log)
├── cli/
│   ├── known_variables.yaml  Seed table for the variable-mapping assist
│   ├── matching.py           Pure fuzzy-matching/detection logic (testable, no I/O)
│   └── create_config.py      `open-csi-config` entry point — interactive + --answers modes
└── api/
    ├── app.py                 create_app() — wires everything into a FastAPI app
    ├── deps.py                 DB session + dataset-location(s) FastAPI dependencies
    ├── auth.py                 Anonymous-auth seam (get_current_user) — OIDC login not built yet
    ├── access.py                is_visible()/require_visible() — the one restricted-dataset gate
    ├── opendap.py                xpublish Plugin serving public datasets via build_dataset()
    ├── schemas.py               JSON response models
    ├── services.py              list_visible_datasets() — the listing/search choke point
    ├── routers/
    │   ├── datasets_api.py       GET /datasets (JSON listing)
    │   ├── pages.py               GET / (listing+map+panel page), GET /map (standalone map)
    │   ├── dataset_detail.py      GET /datasets/{id}[/deployments|/data|/download.nc|/download.csv]
    │   └── publish.py             GET /publish/datasets, GET /publish/{id}/{yyyy-mm} (API-key auth)
    ├── templates/                 Jinja2 templates (base, datasets/list.html, map.html)
    └── static/
        ├── css/site.css
        ├── js/{filter,map,dataset_panel}.js
        └── vendor/leaflet/        Self-hosted Leaflet assets (no external CDN dependency)
```

## The one path every consumer goes through

`core/builder.py::build_dataset(dataset_id, start, end, variables)` is the single
function that turns a dataset id + time range into an `xarray.Dataset`. Every consumer —
the listing page, the REST data/download endpoints, OPeNDAP, and the publish endpoint —
calls this rather than re-implementing data assembly. It:

1. Resolves the current config version (`config_versioning.get_versioned_config`).
2. Lazily refreshes the file index (`index.service.refresh_and_get_index`).
3. Selects only the files whose time range overlaps the request.
4. Reads only the raw columns actually needed (`DataProvider.read_range`).
5. Maps raw columns to canonical variable names (`variable_mapping.apply_variable_spec`).
6. Resolves fixed/mobile deployment metadata (`deployment.apply_deployment_metadata`).

`core/builder.py::resolve_time_coverage()` is the other shared helper — the dataset's
overall observed time range, used by the detail endpoint and the publish endpoint's
month-completeness logic.

## What's built vs. what's planned

Built and tested end-to-end against real UNIS station data:

- The full `build_dataset()` pipeline (LoggerNet source type).
- A **second source type** (`generic_csv`) proving the `ConfigProvider`/`DataProvider`
  plugin boundary is genuinely independent of the core pipeline (§13).
- A server-rendered, filterable dataset-listing page that also embeds a **station map**
  and a **dataset detail panel** (metadata + OPeNDAP/NetCDF/CSV access links) — see
  `docs/rest_api.md` for the endpoints it's built on.
- The **full REST API**: per-dataset metadata, deployment history, ad-hoc data queries
  (JSON/CSV), and full-dataset downloads (NetCDF/CSV) — see `docs/rest_api.md`.
- **OPeNDAP** via `xpublish`/`xpublish-opendap`, public datasets only — see
  `docs/opendap.md` (including a known client-interop caveat).
- The **publish endpoint** (on-demand monthly NetCDF generation + cache, immutable once
  generated, static API-key auth) — see `docs/publish_endpoint.md`.
- A **config-creation CLI** (`open-csi-config`) — see `docs/cli.md`.
- Restricted-dataset **gating** (`api/access.py`) applied consistently across listing,
  detail, data, download, and OPeNDAP — but not the real Entra ID/OIDC **login flow**
  itself: `api/auth.py::get_current_user()` still always resolves to `None` (anonymous).
  That's the one deferred piece — blocked on an external prerequisite (a Microsoft Entra
  ID app registration) that doesn't exist yet. Every endpoint is already gated correctly
  for the day it does.

## Why some things are the way they are

- **`file_pattern` matches the live file only**, not a single wildcard covering live +
  archived variants — LoggerNet table names can be prefixes of each other (`Min` /
  `Min10` / `Min60`), so a loose wildcard risks matching the wrong table's files. See
  `LoggerNetSourceConfig`'s docstring and `providers/data/loggernet/provider.py`.
- **The search/listing index is computed fresh per request**, not cached — dataset
  counts are small enough that this costs nothing, and it reuses the same per-request
  config load the lazy versioning check already does. See `core/search_index.py`.
- **Deployment timestamps are normalized to naive UTC** at config-validation time,
  because raw LoggerNet timestamps carry no timezone information at all and are treated
  as UTC by convention — comparing a tz-aware deployment boundary against a naive data
  timestamp would otherwise raise.
- **`source_config`'s discriminated union keeps `source_type` as a top-level sibling
  field**, not nested inside `source_config` — Pydantic's native discriminated-union
  support wants the discriminator embedded in each union member, but that would have
  required migrating every existing config's JSON shape for no real benefit. A
  `model_validator(mode="before")` resolves it manually instead. See
  `core/config_schema.py`.
- **The publish endpoint checks its cache before re-validating anything else** —
  immutability (a published month is never regenerated) is the load-bearing guarantee,
  so a cache hit skips even the month-settledness check. See `core/publish.py` and
  `api/routers/publish.py`.
- **OPeNDAP is served via `xpublish`/`xpublish-opendap`, not a hand-rolled `pydap`
  handler** — ASGI-native (no WSGI bridging into FastAPI), and its dataset-provider hook
  maps directly onto `build_dataset()`'s signature. See `docs/opendap.md` for the
  trade-offs and a real client-interop caveat found while verifying it.
- **The map is embedded in the listing page by building markers from the
  already-rendered table rows**, not a second `/datasets` fetch — this keeps it
  automatically consistent with whatever filters (server- or client-side) are currently
  active, and a restricted dataset that never got rendered as a row can't get a marker
  either. See `static/js/map.js`.
