# Architecture

For the overall system design — why it's built this way, the full set of planned
consumers (OPeNDAP, downloads, Grafana, the publish endpoint), access control, and the
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
│   ├── config_schema.py      The dataset config envelope (Pydantic)
│   ├── config_versioning.py  Lazy hash-check + snapshot (get_versioned_config)
│   ├── variable_mapping.py   Raw columns -> canonical output variables
│   ├── deployment.py         Fixed position / mobile platform resolution
│   ├── search_index.py       Config -> flattened listing/search document
│   ├── models.py             FileRecord (in-memory file-index entry)
│   └── builder.py            build_dataset() — ties everything above together
├── providers/
│   ├── base.py                ConfigProvider / DataProvider ABCs
│   ├── config/folder.py       FolderConfigProvider (scans *.json in a folder)
│   └── data/loggernet/
│       ├── toa5.py            TOA5 .dat header + body parsing
│       ├── fileset.py         Live/archived file classification + reconciliation
│       └── provider.py        LoggerNetDataProvider (get_file_index / read_range)
├── index/service.py          Lazy file-index refresh orchestration
├── state/                    SQLAlchemy models + repository (config_versions, file_index, publish_log)
└── api/
    ├── app.py                 create_app() — wires everything into a FastAPI app
    ├── deps.py                 DB session + dataset-location FastAPI dependencies
    ├── auth.py                 Anonymous-auth seam (get_current_user)
    ├── schemas.py               JSON response models
    ├── services.py              list_visible_datasets() — the listing/search choke point
    ├── routers/                 datasets_api.py (JSON), pages.py (HTML)
    ├── templates/                Jinja2 templates for the listing page
    └── static/                   CSS + the client-side filter.js
```

## The one path every consumer goes through

`core/builder.py::build_dataset(dataset_id, start, end, variables)` is the single
function that turns a dataset id + time range into an `xarray.Dataset`. Every consumer —
today's listing page, and later REST data/download endpoints, OPeNDAP, and the publish
endpoint — is meant to call this rather than re-implementing data assembly. It:

1. Resolves the current config version (`config_versioning.get_versioned_config`).
2. Lazily refreshes the file index (`index.service.refresh_and_get_index`).
3. Selects only the files whose time range overlaps the request.
4. Reads only the raw columns actually needed (`DataProvider.read_range`).
5. Maps raw columns to canonical variable names (`variable_mapping.apply_variable_spec`).
6. Resolves fixed/mobile deployment metadata (`deployment.apply_deployment_metadata`).

## What's built vs. what's planned

Built and tested end-to-end against real UNIS station data: the full path above, plus a
REST `GET /datasets` endpoint and a server-rendered, filterable listing page.

Not yet built (see `implementation_plan.md`'s §14 roadmap, carried forward at the end of
the original planning document for this phase): per-dataset metadata/data/download
endpoints, the real Entra ID/OIDC login flow behind `api/auth.py`'s seam, the OPeNDAP
handler, the station-track map view, the publish endpoint, a second source type, and the
config-creation CLI.

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
