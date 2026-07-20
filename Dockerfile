# syntax=docker/dockerfile:1

# --- builder ------------------------------------------------------------
# Resolves and installs dependencies + the project itself into a venv via
# uv. Split into two `uv sync` layers so editing source code doesn't bust
# the (much slower) dependency-installation cache layer.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies only first — cached independently of source changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Now the project itself. README.md is only needed because pyproject.toml
# declares it as the package's `readme`. No config (sample_configs/, .env,
# etc.) is ever baked into the image — it's runtime state, supplied entirely
# via volumes/env vars (see docker-compose.yml), same as mount/ and local/.
COPY src/ src/
COPY README.md ./
# --no-editable: uv sync's default editable install of the project itself
# leaves site-packages pointing back at /app/src rather than containing a
# real copy — fine for local dev, broken once only .venv/ (not src/) is
# copied into the runtime stage below.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# --- runtime --------------------------------------------------------------
# No uv, no build tools, no dev dependencies (pytest/ruff/httpx) — just
# python + the venv built above. Debian slim, not alpine: numpy/pandas/h5py
# rely on prebuilt manylinux (glibc) wheels; alpine's musl libc would force
# slow, fragile from-source builds and end up bigger in practice, not
# smaller. Must match the builder's base OS (bookworm) — the copied venv's
# `.venv/bin/python*` symlinks resolve against the base image's own
# interpreter path, which only lines up across these two specific images.
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --system app && useradd --system --gid app --home-dir /app --create-home app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BASE_DIR=/app

# mount/ (real source-station data), sample_configs/ (dataset configs,
# sources.yaml, branding.yaml), and local/ (sqlite state + publish cache) are
# all runtime state, not image contents — see docker-compose.yml's volumes.
# Created here (and owned by the app user) so the container still starts
# cleanly even if nothing is mounted over them, but there's nothing usable to
# serve until sample_configs/ (or your own config dir) is actually mounted.
RUN mkdir -p /app/mount /app/sample_configs /app/local && \
    chown app:app /app/mount /app/sample_configs /app/local

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/datasets')" || exit 1

CMD ["uvicorn", "open_csi_publisher.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
