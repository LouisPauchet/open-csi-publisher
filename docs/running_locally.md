# Running locally

## Start the server

```sh
uv run uvicorn open_csi_publisher.api.app:create_app --factory --reload
```

Then visit `http://127.0.0.1:8000/` for the dataset listing page (which also embeds the
station map and a click-to-select detail panel), or `http://127.0.0.1:8000/map` for the
map on its own. `http://127.0.0.1:8000/datasets` is the JSON API — see
[rest_api.md](rest_api.md) for the full REST surface, [opendap.md](opendap.md) for
OPeNDAP, and [publish_endpoint.md](publish_endpoint.md) for the publish endpoint.

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
| `BRANDING_FILE` | `sample_configs/branding.yaml` | Path (relative to `BASE_DIR`) to the logo/color-set config. See [branding.md](branding.md) — this is what a non-UNIS deployment repoints to reskin the portal. |
| `BASE_DIR` | `.` | Base directory `SOURCES_FILE`, `BRANDING_FILE`, and each source's `config_location`/`data_location` are resolved against. Set this to an absolute path if running from somewhere other than the repo root. |
| `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `SESSION_SECRET_KEY` | unset | Inert placeholders for the future Entra ID/OIDC integration. While `OIDC_ISSUER` is unset (the default), every caller is anonymous and restricted datasets are always hidden — there is currently no way to log in. |
| `PUBLISH_API_KEYS_RAW` | `""` (empty — no keys, endpoint always 401s) | Comma-separated static API keys for the publish endpoint. See [publish_endpoint.md](publish_endpoint.md). |
| `PUBLISH_CACHE_DIR` | `local/publish_cache` | Where generated monthly NetCDF files are cached. |
| `THINGSBOARD_BASE_URL`, `THINGSBOARD_USERNAME`, `THINGSBOARD_PASSWORD` | unset | The single ThingsBoard tenant a `thingsboard` source entry connects to (there's only one — see [config_format.md](config_format.md)). Until all three are set, no `thingsboard` source can be constructed; a deployment with no `thingsboard` entry in `sources.yaml` is unaffected. |
| `THINGSBOARD_DISCOVERY_INTERVAL_SECONDS` | `3600` | How often `list_dataset_ids()` re-probes every tenant device for the `open-csi-publisher-config` attribute (an in-process TTL cache) instead of re-scanning on every request. |

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

After any change to `static/js/map.js` or `static/js/dataset_panel.js`, also check:

8. On `/`, fixed stations show a map marker at their configured position; the mobile
   dataset shows a marker at its most recent real position plus a recent track line.
9. Typing a filter that hides a row also hides that dataset's map marker (and
   re-showing the row re-shows the marker) — `filter.js` and `map.js` staying in sync.
10. Clicking a table row (or a map marker) opens the detail panel with the right title,
    metadata, and three working links: OPeNDAP structure (DDS), download NetCDF,
    download CSV — and highlights the selected row.

After any change to `site.css`'s layout rules (`.portal-layout`, `#dataset-panel`,
`.dataset-table-wrap`), also check:

11. The browser window/page itself never grows a scrollbar — the header stays put, and
    the map, dataset table, and detail panel each fill their own space.
12. On `/`, the dataset table scrolls on its own (mouse over the table) without moving
    the filter form above it; the column headers stay pinned while scrolling.
13. Select a dataset with a lot of metadata (or temporarily add a few dummy fields to a
    sample config) — the metadata list inside the panel scrolls on its own, while the
    title, description, date-range inputs, and download links above/below it stay put.
14. Resize the window below ~900px wide (or use a mobile viewport) — the layout falls
    back to a normal scrolling page instead of the fixed-height two-column layout.
