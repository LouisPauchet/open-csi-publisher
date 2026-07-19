# Setup

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for dependency management and running commands
- Python 3.12+ (uv will install a matching interpreter automatically if needed)

## Install

```sh
uv sync --group dev
```

This creates `.venv/` and installs both runtime dependencies (FastAPI, xarray, pandas,
SQLAlchemy, ...) and dev dependencies (pytest, httpx, ruff).

## Run the tests

```sh
uv run pytest                # fast tests
uv run pytest -m slow        # opt-in slow tests (parses a 444MB real sample file)
uv run pytest -m "not slow"  # explicitly exclude slow tests
```

Most tests run against the real LoggerNet sample data in `mount/loggernet-test-server/`
(gitignored, not tracked in the repo). Tests that need it are automatically skipped if
that directory is absent — the suite still runs cleanly (with those tests skipped) in an
environment that doesn't have the sample data, e.g. CI.

## Repo layout

```
sample_configs/    Tracked dataset configs (3 real stations) + sources.yaml
mount/             Gitignored real LoggerNet sample data (not tracked)
local/             Gitignored local dev state (sqlite DB, etc.)
src/open_csi_publisher/
  core/            Config schema, versioning, variable mapping, deployment
                    resolution, search indexing, the core builder
  providers/       ConfigProvider/DataProvider implementations (LoggerNet)
  index/           Lazy file-index refresh orchestration
  state/           SQLAlchemy models + repository (config versions, file index)
  api/             FastAPI app: routes, templates, static assets
tests/             pytest, mirrors src/open_csi_publisher/
docs/              This documentation
```

See [architecture.md](architecture.md) for what each module actually does.
