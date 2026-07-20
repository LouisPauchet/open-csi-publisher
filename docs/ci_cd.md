# CI/CD

Two workflows: `.github/workflows/ci.yml` validates every push/PR;
`.github/workflows/release-please.yml` handles versioning and is the only thing that
ever pushes an image to the registry.

## `ci.yml` — validate

Triggers: `push` to `main`, `pull_request` targeting `main`, manual (`workflow_dispatch`).
Runs are cancelled/superseded by a newer push to the same branch/PR (`concurrency`).

- **`lint`** — `uv run ruff check .`. Matches the ruleset already configured in
  `pyproject.toml`'s `[tool.ruff]`; nothing CI-specific.
- **`test`** — `uv run pytest -q`. No real station data (`mount/`) exists in CI —
  `mount`-dependent tests self-skip via the `requires_mount` marker (`tests/conftest.py`),
  same as on any contributor's machine without the real mount present.
- **`docker`** — `docker build` only, gated on `lint`/`test` passing, **never pushes**.
  Catches a broken `Dockerfile` before merge without publishing anything untested.

## `release-please.yml` — version and publish

Triggers on every `push` to `main`. Two jobs:

1. **`release-please`** ([`googleapis/release-please-action`](https://github.com/googleapis/release-please-action)) —
   parses [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
   `feat!:`/`BREAKING CHANGE:`, ...) since the last release and keeps a standing
   `chore(main): release X.Y.Z` PR open, whose diff bumps `pyproject.toml`'s `version`
   (PEP 621 `[project]` table — `release-type: python` in `release-please-config.json`
   supports this directly) and appends to `CHANGELOG.md`. Most pushes to `main` just
   update that PR and stop there — nothing else fires.

   **Merging that PR is the actual release**: the merge is itself a push to `main`, so
   this job runs again, recognizes its own PR was merged, creates the `vX.Y.Z` tag and a
   GitHub Release, and reports `release_created: true`.

2. **`docker-publish`** — `needs: release-please`, runs only when
   `release_created == 'true'`. Builds and pushes to `ghcr.io/<owner>/<repo>`, tagged
   `latest`, `X.Y.Z`, `X.Y`, and `X` — all sourced directly from release-please's own
   `major`/`minor`/`patch` outputs, not re-parsed from a ref string. `pyproject.toml`'s
   `version` and the image tag are the same number by construction (release-please wrote
   both), so there's no separate "keep the release version in sync with pyproject.toml"
   step to maintain.

**No manual tag pushes** — release-please owns the whole version lifecycle: what the next
version number is (from commit messages), writing it into `pyproject.toml`, tagging it,
and creating the GitHub Release. A human only has to (a) write reasonably-conventional
commit messages and (b) merge the release PR when ready to ship.

## Configuration is never part of the image

`sample_configs/` (dataset configs, `sources.yaml`, `branding.yaml`) — and anything else
environment-specific — is deliberately excluded from the build context (`.dockerignore`)
and never `COPY`'d in the `Dockerfile`. The image is the same regardless of which
deployment runs it; each deployment supplies its own config entirely via volumes/env vars
at `docker run`/`docker compose` time. See [docker.md](docker.md).

## Permissions

- `release-please.yml`'s `release-please` job needs `contents: write` +
  `pull-requests: write` (to open/update the release PR and create the tag/release).
- Its `docker-publish` job needs `packages: write` (scoped to that job only) to push to
  GHCR using the automatic `GITHUB_TOKEN` — no PAT/secret setup required.
- `ci.yml` needs neither — it only ever builds, never pushes anywhere.

If a repo's default "Workflow permissions" setting is read-only, these job-level
`permissions:` blocks are what actually grant the write access; no other repo
configuration is needed for a first-party (non-fork) repo.

## Running it locally before pushing

```sh
uv run ruff check .
uv run pytest -q
docker build -t open-csi-publisher:local .
```
