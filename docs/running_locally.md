# Running locally

## Start the server

```sh
uv run uvicorn open_csi_publisher.api.app:create_app --factory --reload
```

Then visit `http://127.0.0.1:8000/` for the dataset listing page, or
`http://127.0.0.1:8000/datasets` for the JSON API.

On first request, this creates `local/state.db` (a SQLite file, gitignored) holding
config version snapshots and the file index — safe to delete at any time to reset local
state; it will be recreated automatically.

## Environment variables

All optional; sensible defaults assume you're running from the repo root with the real
sample data present under `mount/`.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./local/state.db` | State store connection string. Point this at a PostgreSQL URL for prod-like testing (`postgresql+psycopg://...`) — the same SQLAlchemy models work against both. |
| `SOURCES_FILE` | `sample_configs/sources.yaml` | Path (relative to `BASE_DIR`) to the sources manifest. |
| `BASE_DIR` | `.` | Base directory `SOURCES_FILE` and each source's `config_location`/`data_location` are resolved against. Set this to an absolute path if running from somewhere other than the repo root. |
| `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `SESSION_SECRET_KEY` | unset | Inert placeholders for the future Entra ID/OIDC integration. While `OIDC_ISSUER` is unset (the default), every caller is anonymous and restricted datasets are always hidden — there is currently no way to log in. |

## Manual QA checklist

Automated tests cover the server-rendered filtering and the served JS content, but not
that the client-side script actually runs correctly in a browser. After any change to
`static/js/filter.js` or the listing template, check manually:

1. Open `/` in a browser with JavaScript enabled.
2. Type into the search box — rows should hide/show **instantly**, with no page reload
   and no network request (check the browser's network tab).
3. Toggle the platform-type and variable dropdowns — same instant behavior.
4. Fill in a metadata key + value — same.
5. Clear all filters — all rows reappear.
6. Disable JavaScript (or open with `?platform_type=mobile` etc. directly in the URL) and
   confirm the page still renders the correctly filtered set via a normal page load —
   the server-side filtering is authoritative and must work standalone.
7. Submit the form (press Enter, or click Filter) with JS enabled — confirm the URL
   updates with query params and a full reload still shows the same filtered result the
   client-side JS was already showing.
