# Docker

## Quick start

```sh
docker compose up -d --build
```

Serves the app at `http://127.0.0.1:8000/`, using the real `mount/` station data and
`sample_configs/` already in the repo (see [running_locally.md](running_locally.md) for
what those need to contain).

## Image

Multi-stage build (`Dockerfile`):

- **builder** — `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`, resolves and installs
  dependencies + the project itself into a venv via `uv sync --frozen`. Split into a
  dependencies-only layer and a project-install layer so editing source code doesn't
  invalidate the (much slower) dependency-installation cache.
- **runtime** — plain `python:3.12-slim-bookworm` (matched to the builder's own base so
  the copied venv's interpreter symlinks still resolve), with just the built venv copied
  in — no `uv`, no compilers, no dev dependencies (pytest/ruff/httpx). Runs as a non-root
  user.

**Debian slim, not alpine, deliberately**: numpy/pandas/h5py rely on prebuilt manylinux
(glibc) wheels; alpine's musl libc has no reliable prebuilt wheels for this stack, which
would force slow, fragile from-source builds (needing a large compiler toolchain at
build time) and typically ends up *larger*, not smaller, once actually built. The
resulting image is ~555MB — the base `python:3.12-slim-bookworm` alone is ~190MB, so the
app's own dependency footprint (numpy/pandas/xarray/h5py/sqlalchemy/fastapi/xpublish) is
the other ~365MB, which is in line for that stack.

**No configuration is ever baked into the image** — `sample_configs/` (dataset configs,
`sources.yaml`, `branding.yaml`) is supplied entirely via the `docker-compose.yml` bind
mount below, same as `mount/` and `local/`. This keeps the built image
environment-agnostic (safe to build once in CI and push to a registry, then run against
any deployment's own config) and means editing configs on the host takes effect
immediately, without a rebuild — consistent with the app's own lazy config-versioning
(hash-check) design. The container has nothing usable to serve until a config directory
is actually mounted over `/app/sample_configs`.

## Volumes (`docker-compose.yml`)

| Host path | Container path | Purpose |
|---|---|---|
| `./mount` | `/app/mount` (read-only) | Real source-station data (LoggerNet `.dat`/`.dat.backup` files). Never baked into the image. |
| `./sample_configs` | `/app/sample_configs` (read-only) | Dataset configs + `sources.yaml`/`branding.yaml`. The app server only ever reads these — `open-csi-config` (which writes them) is meant to run on the data-collection server, per [cli.md](cli.md). |
| `./local` | `/app/local` | The app's only writable, persisted state: the SQLite state db and the publish endpoint's generated NetCDF cache. |

## Environment variables

`docker-compose.yml`'s `environment:` block maps every `Settings` field from
[running_locally.md](running_locally.md)'s table. `BASE_DIR` is set to `/app` (the
image's `WORKDIR`) so the relative `SOURCES_FILE`/`BRANDING_FILE`/`PUBLISH_CACHE_DIR`
defaults resolve correctly inside the container.

The image always includes the `postgres` extra (psycopg), so switching from the default
SQLite is just a `DATABASE_URL` change — no rebuild, and no special step for anyone
running the already-published image (e.g. pulled from GHCR):

```yaml
DATABASE_URL: postgresql+psycopg://user:password@postgres:5432/open_csi_publisher
```

## Subpath deployment (`ROOT_PATH`)

Set `ROOT_PATH` (e.g. `/csi-publisher`) when this app should live at
`https://host/csi-publisher/` instead of the domain root. It prefixes every outbound URL
this app hands back to the browser — static assets, nav links, the OIDC redirect_uri, and
the publish endpoint's `download_url` (see [running_locally.md](running_locally.md)'s
settings table).

**The reverse proxy must strip the prefix** before forwarding to the container — this app's
own routes are always served un-prefixed (`/`, `/static/...`, `/opendap/...`), and `ROOT_PATH`
only controls what the app writes into links, not how it routes requests. A minimal nginx
example:

```nginx
location /csi-publisher/ {
    proxy_pass http://open-csi-publisher:8000/;
    proxy_set_header Host $host;
}
```

(the trailing `/` on both `location` and `proxy_pass` is what makes nginx strip the prefix).
Then set `ROOT_PATH: "/csi-publisher"` in `docker-compose.yml`'s `environment:` block to
match. Left unset (the default), the app behaves exactly as if mounted at the domain root —
no proxy required.

## Manual verification

```sh
docker compose up -d --build
curl -s http://127.0.0.1:8000/datasets
docker compose logs -f
docker compose down
```
