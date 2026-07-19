# Config-creation CLI

`implementation_plan.md` §15. Scoped to LoggerNet first. Installed as the
`open-csi-config` entry point (`uv run open-csi-config`), or run directly:
`uv run python -m open_csi_publisher.cli.create_config`.

**Runs on the data-collection server** (needs write access to the mount), not the
read-only app server — same package, different invocation host.

## Interactive mode

```sh
uv run open-csi-config --data-root mount/loggernet-test-server --output-dir sample_configs
```

Walks through: dataset id, file-pattern discovery (glob against `--data-root`, refined
until it resolves to exactly one live `.dat` file), a TOA5 header scan (reusing
`providers/data/loggernet/toa5.py::parse_toa5_header` — no duplicate parser), a
variable-mapping assist (fuzzy-matched against `cli/known_variables.yaml`, confirm or
skip each), GPS-column detection (offers `platform_type: mobile` if found),
extra-dimension grouping detection (offers to combine leveled columns like
`AirTC_2m_Avg`/`AirTC_10m_Avg` into one variable), deployment/metadata/access prompts,
then validates against `DatasetConfig` and writes `<id>.json`.

**Re-running against an existing dataset id** (e.g. after a sensor swap changed a raw
column name) compares newly-scanned columns against the existing config's
`raw_name`/`old_names` and reports each as already-mapped, a likely rename, or
genuinely new — so you're not starting from scratch.

## Non-interactive mode

For scripted/bulk config creation, supply a JSON answers file instead of prompts:

```sh
uv run open-csi-config --answers answers.json --output-dir sample_configs
```

```json
{
  "id": "new_station",
  "file_pattern": "New_Station/New_Station_Table.dat",
  "table_name": "Table",
  "variables": [
    {"raw_name": "AirT_C", "standard_name": "air_temperature", "units": "degC"}
  ],
  "platform_type": "fixed",
  "deployments": [{"start": "2026-01-01T00:00:00Z", "end": null, "lat": 78.0, "lon": 15.0}],
  "metadata": {"title": "New Station"},
  "access": "public"
}
```

See `open_csi_publisher/cli/create_config.py::build_config_dict()` for exactly which
keys are recognized and their defaults. Validation failures print a clear error and
exit non-zero without writing anything; an existing `<id>.json` is left untouched
unless `--force` is passed.

## Extending `known_variables.yaml`

`src/open_csi_publisher/cli/known_variables.yaml` is a plain, editable reference file
(raw column name → `{standard_name, units}`), not hardcoded into the CLI — add entries
as new sensor naming conventions are encountered.
