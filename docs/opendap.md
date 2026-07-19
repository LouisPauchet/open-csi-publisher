# OPeNDAP

Public datasets only — a restricted dataset is never registered with the OPeNDAP
handler at all (not merely blocked), matching `implementation_plan.md` §8.

## URLs

Built on `xpublish` + `xpublish-opendap`, mounted at `/opendap`. Because xpublish owns
the dataset-scoped route prefix (`/datasets/{dataset_id}`) and the OPeNDAP plugin adds
its own `/opendap` prefix on top, the full URL ends up with a doubled `opendap` segment:

```
http://<host>/opendap/datasets/<dataset_id>/opendap.dds    # variable/dimension structure
http://<host>/opendap/datasets/<dataset_id>/opendap.das    # attributes
http://<host>/opendap/datasets/<dataset_id>/opendap.dods   # binary data
```

The base URL an OPeNDAP client is given to *open* the dataset is the `.dds`/`.das`
suffix stripped: `http://<host>/opendap/datasets/<dataset_id>/opendap`.

`GET /opendap/datasets` lists every public dataset id currently servable.

## Caching

`api/opendap.py::PortalDatasetProvider` caches the built `xarray.Dataset` for 60
seconds (a `cachetools.TTLCache`) to absorb repeated polling (Grafana, repeated client
opens) without rebuilding on every request. `xpublish-opendap` itself also caches the
DAP-protocol-converted representation for much longer (~27.7h, internal to that
library) once it's been resolved once.

**Known limitation**: neither cache layer is aware of DAP constraint expressions
(hyperslab/variable selection) — `build_dataset()` is always called for a dataset's
*full* available time range on a cache miss, not the specific slice a client requested.
For a dataset whose full history is very large, this means the first request (or first
request after the TTL expires) pays the cost of building everything. Acceptable for now
given real dataset sizes measured so far (see `implementation_plan.md`'s seek-index
notes); revisit by forking/customizing `xpublish-opendap`'s router to parse the
constraint before calling the dataset-provider hook, if this becomes a real problem.

## Known client-interop caveat

Verified by hand against a real running server (not just the automated test suite,
which uses FastAPI's `TestClient` and doesn't exercise real HTTP chunked-transfer
behavior): `.dds`/`.das` metadata and the raw `.dods` byte stream are protocol-correct
and complete — confirmed independently via `curl` and Python's `requests` library
reproducing the exact request sequence a real client makes.

However, `xr.open_dataset(url, engine="pydap")` — the `pydap` package specifically —
reproducibly failed reading variable data with `ChunkedEncodingError: Response ended
prematurely`, on every attempt, regardless of dataset size or URL scheme (`http://` vs.
the `dap2://` scheme `pydap` itself suggests). The root cause wasn't isolated in the
time available — payload truncation and `pydap`-side `Range`-header usage were both
ruled out. Treat this as an open item if `pydap`-based tooling is a required client;
other DAP2 clients (raw `curl`/`wget`, or tools built on other HTTP libraries) were not
observed to have this problem. See `api/opendap.py`'s module docstring for the same
note, kept in sync with this page.

## Manual verification

```sh
uv run uvicorn open_csi_publisher.api.app:create_app --factory --reload
curl http://127.0.0.1:8000/opendap/datasets
curl http://127.0.0.1:8000/opendap/datasets/<dataset_id>/opendap.dds
```
