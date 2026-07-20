# Adding a dataset

There's no config-creation CLI yet (planned — see `implementation_plan.md` §15); for now,
configs are written by hand against `FolderConfigProvider`, which scans
`sample_configs/` for `<dataset_id>.json` files (in production, this would point at a
site's `__config__/` folder instead — see `sources.yaml`).

## Steps

1. **Locate the raw files.** Find the station's `.dat` file(s) on the mount and note the
   exact live filename (e.g. `StationName_Table.dat`) and whether an archived twin exists
   (`StationName_Table_Historical.dat` and/or `StationName_Table.dat.backup`).

2. **Read the header.** The first 4 lines of a TOA5 `.dat` file are: station/logger info,
   column names, units, and aggregation type. You can inspect this directly:

   ```sh
   uv run python -c "
   from pathlib import Path
   from open_csi_publisher.providers.data.loggernet.toa5 import parse_toa5_header
   h = parse_toa5_header(Path('mount/loggernet-test-server/<station>/<file>.dat'))
   print(h.column_names)
   print(h.units)
   "
   ```

3. **Write the config.** Create `sample_configs/<dataset_id>.json` — see
   [config_format.md](config_format.md) for the shape, and the existing 3 files for
   worked examples covering the fixed, mobile, and archived-file cases. The `id` field
   must match the filename.

4. **Validate it loads and passes schema validation:**

   ```sh
   uv run python -c "
   from pathlib import Path
   from open_csi_publisher.core.config_schema import DatasetConfig
   from open_csi_publisher.providers.config.folder import FolderConfigProvider
   provider = FolderConfigProvider(Path('sample_configs'))
   config = DatasetConfig.model_validate(provider.load_config('<dataset_id>'))
   print(config.id, config.platform_type, len(config.variables))
   "
   ```

5. **Build it end-to-end** against real data, to confirm the file_pattern actually
   matches and the variable mappings produce sane output:

   ```sh
   uv run python -c "
   from pathlib import Path
   from sqlalchemy.orm import Session
   from open_csi_publisher.core.builder import build_dataset
   from open_csi_publisher.providers.config.folder import FolderConfigProvider
   from open_csi_publisher.providers.data.loggernet.provider import LoggerNetDataProvider
   from open_csi_publisher.state.db import get_engine, init_db

   engine = get_engine('sqlite:///:memory:')
   init_db(engine)
   with Session(engine) as session:
       ds = build_dataset(
           '<dataset_id>', session=session,
           config_provider=FolderConfigProvider(Path('sample_configs')),
           data_provider=LoggerNetDataProvider(Path('mount/loggernet-test-server')),
       )
       print(ds)
   "
   ```

6. **Check it shows up on the listing page** — run the server
   ([running_locally.md](running_locally.md)) and confirm the new dataset appears at `/`
   with the expected title, platform type, and variables.

## Re-adding an existing dataset (sensor rename, new column)

If a column's raw name changed (sensor swap, logger reprogram), add the old name to that
variable's `old_names` list rather than treating it as unmapped — this coalesces the two
periods into one continuous output variable (see `variable_mapping.py`). A genuinely new
column just needs a new `variables[]` entry; nothing else needs to change.

## Adding a ThingsBoard-backed dataset

There's no CLI support for this source type yet (`open-csi-config` stays LoggerNet-only)
— configs are authored by hand against the shape documented in
[config_format.md](config_format.md#source_config-thingsboard).

1. **Locate/confirm the device in ThingsBoard.** Note its exact device name — this
   becomes both `source_config.device_name` and the config's own `id`.
2. **Set the config attribute.** In the ThingsBoard UI, open the device → Attributes →
   Server attributes, and add (or edit) an attribute named `open-csi-publisher-config`
   whose value is the full dataset config JSON (`source_type: "thingsboard"`,
   `source_config: {"device_name": "<exact device name>"}`, plus `variables`,
   `platform_type`, `deployments`, `metadata`, `output` — same shape as any other
   dataset). `variables[].raw_name` should match this device's telemetry key names.
3. **Add a `thingsboard` entry to your own deployment's `sources.yaml`** (not
   `sample_configs/sources.yaml` in this repo — that file intentionally has no live
   ThingsBoard entry, see `docs/architecture.md`):

   ```yaml
   sources:
     - id: thingsboard_svalbard
       type: thingsboard
       config_provider: thingsboard
       config_location: ""
       data_location: ""
       credentials_env_prefix: THINGSBOARD_SVALBARD
   ```

   `config_location`/`data_location` are unused for this source type (the connection
   comes from environment variables, not a folder path) — set to empty strings.
   `credentials_env_prefix` names which env vars hold *this* entry's ThingsBoard
   credentials (step 4) — it defaults to `THINGSBOARD` if omitted, so a single-tenant
   setup can skip it entirely. **Multiple ThingsBoard tenants are supported**: add one
   `thingsboard` source entry per tenant, each with its own `id` and a distinct
   `credentials_env_prefix` (e.g. `THINGSBOARD_SVALBARD`, `THINGSBOARD_NY_ALESUND`).
4. **Set the connection env vars**, named after the prefix from step 3 — for
   `credentials_env_prefix: THINGSBOARD_SVALBARD`, that's `THINGSBOARD_SVALBARD_BASE_URL`,
   `THINGSBOARD_SVALBARD_USERNAME`, `THINGSBOARD_SVALBARD_PASSWORD` (see
   [running_locally.md](running_locally.md)). A second tenant just needs its own prefix
   and its own three env vars — nothing else changes. Put these in a gitignored file
   under `local/` (e.g. `local/.env`), **not** a root-level `.env`, which
   pydantic-settings loads unconditionally and would leak a customized `SOURCES_FILE`
   into the test suite — load it explicitly per-invocation instead, via
   `uv run --env-file local/.env ...` (both commands below).
5. **Validate it loads:**

   ```sh
   uv run --env-file local/.env python -c "
   from open_csi_publisher.providers.config.thingsboard import ThingsBoardConfigProvider
   from open_csi_publisher.sources import _get_thingsboard_client
   from open_csi_publisher.core.config_schema import DatasetConfig

   provider = ThingsBoardConfigProvider(_get_thingsboard_client('THINGSBOARD_SVALBARD'))
   print(provider.list_dataset_ids())
   config = DatasetConfig.model_validate(provider.load_config('<device_name>'))
   print(config.id, config.platform_type, len(config.variables))
   "
   ```
6. **Check it shows up on the listing page** — start the server with your `sources.yaml`
   ([running_locally.md](running_locally.md)) and confirm the dataset appears at `/` with
   real telemetry once you open its detail panel. Note that newly added/removed devices
   can take up to `THINGSBOARD_DISCOVERY_INTERVAL_SECONDS` (default 1 hour) to
   appear/disappear from the listing — discovery is throttled, not re-run per request.
