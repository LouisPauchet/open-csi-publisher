# Publish endpoint

For the downstream data center to pull the latest complete monthly NetCDF per
dataset, on demand — `implementation_plan.md` §11. Only datasets with
`output.publish: true` in their config are exposed here.

## Auth

A **separate, simpler mechanism** from the OIDC session flow used elsewhere
(`api/auth.py`) — a small number of trusted server-to-server consumers, not end users.
Static API keys, checked against `Authorization: Bearer <key>`:

```sh
export PUBLISH_API_KEYS_RAW="key-one,key-two"
```

(comma-separated; see `settings.publish_api_keys`). A valid key authorizes access to
any `publish: true` dataset regardless of its `access` (`public`/`restricted`) flag —
this is a deliberately separate trust boundary from end-user sessions, not layered on
top of `require_visible()`.

## `GET /publish/datasets`

Lists publishable datasets with their latest **settled** month:

```json
[{"dataset_id": "kapp_thordsen_10minute", "latest_complete_month": "2026-06",
  "download_url": "/publish/kapp_thordsen_10minute/2026-06"}]
```

`latest_complete_month` is `null` if no month is settled yet (e.g. the dataset's data
hasn't left its first month).

## `GET /publish/{dataset_id}/{yyyy-mm}`

Returns the NetCDF for that month, generating it on first request. A month is
**settled** (`core/publish.py::is_month_settled`) once data has actually been observed
continuing past its end — not merely because wall-clock time has passed it — checked
against a freshly-refreshed file index. Requesting an unsettled month returns `409`.

**Immutability**: once a month has been generated, it's served from cache
unconditionally forever — the cache is checked *before* anything else, including
before re-validating settledness or re-reading the current config. If the underlying
config changes later, already-published months are **not** regenerated; a NetCDF
generated last month reflects last month's config, permanently. This is deliberate
(`implementation_plan.md` §4.4) — a correction, if ever needed, is a manual action, not
something this endpoint does automatically.

Generated files carry provenance attributes: `processing_software_version`,
`config_hash`, `config_version_timestamp`. Cached under
`{settings.publish_cache_dir}/{dataset_id}/` (default `local/publish_cache/`,
gitignored like the rest of `local/`).

## Manual verification

```sh
curl -H "Authorization: Bearer key-one" http://127.0.0.1:8000/publish/datasets
curl -H "Authorization: Bearer key-one" \
  http://127.0.0.1:8000/publish/kapp_thordsen_10minute/2026-06 -o out.nc
```
