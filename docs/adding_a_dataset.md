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
