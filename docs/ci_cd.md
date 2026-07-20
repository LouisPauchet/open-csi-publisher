# CI/CD

One workflow, `.github/workflows/ci.yml`, three jobs.

## Triggers

- `push` to `main`
- `push` of a `v*.*.*` tag (e.g. `v1.2.0`)
- `pull_request` targeting `main`
- manual (`workflow_dispatch`)

Runs are cancelled/superseded by a newer push to the same branch/PR (`concurrency`), so
only the latest commit's run matters.

## Jobs

- **`lint`** — `uv run ruff check .`. Matches the ruleset already configured in
  `pyproject.toml`'s `[tool.ruff]`; nothing CI-specific.
- **`test`** — `uv run pytest -q`. No real station data (`mount/`) exists in CI —
  `mount`-dependent tests self-skip via the `requires_mount` marker (`tests/conftest.py`),
  same as on any contributor's machine without the real mount present.
- **`docker`** — builds the image (`docker/build-push-action`), and additionally **pushes**
  it to `ghcr.io/<owner>/<repo>` when the trigger was a `push` (main or a version tag) —
  not on `pull_request` (including PRs from forks, which don't get a package-write
  token anyway). PRs still get the build itself, gated on `lint`/`test` passing first, so
  a broken `Dockerfile` is caught before merge even though nothing is pushed.

  Image tags (`docker/metadata-action`): the branch name, `sha-<short-sha>` (always),
  `latest` (only on `main`), and semver tags (`X.Y.Z` + `X.Y`) when triggered by a
  `v*.*.*` tag push.

## Configuration is never part of the image

`sample_configs/` (dataset configs, `sources.yaml`, `branding.yaml`) — and anything else
environment-specific — is deliberately excluded from the build context (`.dockerignore`)
and never `COPY`'d in the `Dockerfile`. The image built and pushed by this pipeline is the
same image regardless of which deployment runs it; each deployment supplies its own
config entirely via volumes/env vars at `docker run`/`docker compose` time. See
[docker.md](docker.md).

## Permissions

The `docker` job needs `packages: write` (scoped to that job only, not the whole
workflow) to push to GHCR using the automatic `GITHUB_TOKEN` — no PAT/secret setup
required. If a repo's default "Workflow permissions" setting is read-only, this job-level
`permissions:` block is what actually grants the write access; no other repo
configuration is needed for a first-party (non-fork) push/tag build.

## Running it locally before pushing

```sh
uv run ruff check .
uv run pytest -q
docker build -t open-csi-publisher:local .
```
