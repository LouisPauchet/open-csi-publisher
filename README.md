# open-csi-publisher

A data portal for environmental monitoring stations, built for the [University Centre
in Svalbard (UNIS)](https://www.unis.no). Turns raw LoggerNet station files into a
browsable, filterable dataset catalog with a station map, and serves the data itself —
REST (JSON/CSV), OPeNDAP, full NetCDF/CSV downloads, and an on-demand monthly-NetCDF
publish endpoint — all from the same config-driven pipeline.

Not UNIS-specific by design: the visual branding (logo, colors, fonts) is config-driven
(see [docs/branding.md](docs/branding.md)), and the source-data pipeline is built around
a `ConfigProvider`/`DataProvider` plugin boundary — LoggerNet is the one real
implementation today, but it's not architecturally special.

## Features

- **Dataset listing page** — server-rendered, filterable by platform type, variable, and
  arbitrary metadata fields, with an embedded station map and a click-to-inspect detail
  panel (metadata, description, deployment history, and compact download/OPeNDAP/JSON
  access icons).
- **REST API** — per-dataset metadata, deployment history, ad-hoc data queries
  (JSON/CSV, optionally time- and variable-filtered), and full-dataset downloads
  (NetCDF/CSV) with a `#`-commented metadata+provenance header. See
  [docs/rest_api.md](docs/rest_api.md).
- **OPeNDAP** — standard DAP2 access via `xpublish`/`xpublish-opendap`, so the data opens
  directly in `xarray`, Panoply, or any other DAP client. See
  [docs/opendap.md](docs/opendap.md).
- **Publish endpoint** — API-key-protected, on-demand generation of immutable monthly
  NetCDF files for downstream consumers. See
  [docs/publish_endpoint.md](docs/publish_endpoint.md).
- **Config-creation CLI** (`open-csi-config`) — scans a station's raw files and helps
  build/update its dataset config interactively. See [docs/cli.md](docs/cli.md).
- **Restricted-dataset access control** — a small, consistently-applied gate
  (`api/access.py`) across every endpoint; anonymous users never see a restricted
  dataset exists. Real Entra ID/OIDC login is a deferred, planned piece — see
  [implementation_plan.md](implementation_plan.md).

## Quick start

**Docker** (fastest way to see it running):

```sh
docker compose up -d --build
```

See [docs/docker.md](docs/docker.md).

**Local dev**, with [uv](https://docs.astral.sh/uv/):

```sh
uv sync --group dev
uv run uvicorn open_csi_publisher.api.app:create_app --factory --reload
```

Then visit `http://127.0.0.1:8000/`. See [docs/setup.md](docs/setup.md) and
[docs/running_locally.md](docs/running_locally.md) for details, environment variables,
and the manual QA checklist.

## Documentation

Start at [docs/README.md](docs/README.md) for the full documentation index. The overall
system design — why it's built this way, the plugin boundaries, access control, and the
full roadmap — lives in [implementation_plan.md](implementation_plan.md); the pages under
`docs/` document the implementation as it exists today and how to work with it.

## Tests

```sh
uv run pytest
```

Test-first throughout, grounded in real UNIS station sample data wherever possible
rather than synthetic fixtures. See [docs/setup.md](docs/setup.md).
