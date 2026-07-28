# LoggerNet config template

A copy-paste starting point for a new `loggernet` dataset config (see
[config_format.md](config_format.md) for the full field-by-field spec). This one file
demonstrates all three `variables[]` shapes side by side — 0, 1, and 2 `extra_dimension`
levels — plus the metadata keys this pipeline's downstream consumers expect on every
dataset. Every `raw_name` here is a placeholder; swap them for your station's actual
TOA5 column names.

## The three variable shapes

- **0 extra dimensions** — a plain column, one raw name in, one output variable out
  (`AirT_C`, `RH`, `BP_mbar`, `WindDir` below). `dtype: "string"` (see `Sensor_Status`)
  is the same shape, just for non-physical flag/status columns — no `standard_name`/
  `units` needed.
- **1 extra dimension** — several raw columns stacked into one output variable along a
  new coordinate (`WS_2m_ms`/`WS_10m_ms` → `wind_speed(time, height)` below). Use this
  when the same quantity is measured at more than one height/depth/etc.
- **2 extra dimensions** — same idea, crossed along two coordinates at once
  (`Pyr_*_ch*` → `surface_downwelling_shortwave_flux_in_air(time, height, channel)`
  below). Each member's `dimension_value` becomes a `[height, channel]` pair instead of
  a scalar.

Not every raw column needs an entry in `variables[]` — anything not listed is simply
dropped from the output.

## Mandatory metadata keys

`DatasetConfig.metadata` only strictly requires `title` (see `MetadataSpec` in
`core/config_schema.py`) — everything else is schema-optional. The keys below, though,
are what this pipeline's downstream consumers (the listing page's metadata filter, and
whatever archives/re-publishes this data) actually expect populated on every dataset, so
treat them as mandatory in practice. The values shown are a real example, not a
placeholder set — replace them with your own station's details, but keep every key.
Extra keys beyond this set are always welcome (e.g. `naming_authority` if this
deployment is the formal publisher of record — see `config_format.md`).

## Full example

The block below is **JSONC** (JSON + `//` comments) purely so the possible values for
each enum-like field can be explained inline. Strip every `//...` comment before saving
this as a real `.json` config — the loader uses `json.load`/pydantic, not a JSON5 parser,
so a real config file must be strict JSON. The uncommented, copy-paste-ready version is
identical minus the comments — see [config_format.md](config_format.md) if you want the
full prose spec instead of inline notes.

```jsonc
{
  "id": "example_station_10minute",
  "source_type": "loggernet",       // "loggernet" | "generic_csv" | "thingsboard"
  "access": "public",               // "public" | "restricted" — restricted datasets are
                                     // invisible in listings and blocked on every other
                                     // endpoint (detail/data/downloads/OPeNDAP) for
                                     // anonymous callers
  "source_config": {
    "file_pattern": "ExampleStation/ExampleStation_Table_10minute.dat",
    "table_name": "Table_10minute"
  },
  "variables": [
    {"raw_name": "AirT_C", "standard_name": "air_temperature", "units": "degC"},
    {"raw_name": "RH", "standard_name": "relative_humidity", "units": "%"},
    {"raw_name": "BP_mbar", "standard_name": "air_pressure", "units": "mbar"},
    {"raw_name": "WindDir", "standard_name": "wind_from_direction", "units": "degrees"},
    {
      "raw_name": "Sensor_Status",
      "dtype": "string"               // "numeric" (default, omit this key) | "string" —
                                       // use "string" for non-physical flag/status
                                       // columns; no standard_name/units needed then
    },
    {
      "extra_dimension": {"name": "height", "units": "m"},
      "members": [
        // dimension_value is normally numeric (a height/depth/etc.), but can be a
        // string instead for named categories, e.g. "average"/"maximum" — see
        // config_format.md's extra_dimension section for that variant
        {"raw_name": "WS_2m_ms", "dimension_value": 2},
        {"raw_name": "WS_10m_ms", "dimension_value": 10}
      ],
      "standard_name": "wind_speed",
      "units": "m/s"
    },
    {
      // 2+ dimensions: extra_dimension becomes an array, and each member's
      // dimension_value becomes a same-length array (one value per dimension, in the
      // same order as extra_dimension) instead of a scalar
      "extra_dimension": [
        {"name": "height", "units": "m"},
        {"name": "channel", "units": "1"}
      ],
      "members": [
        {"raw_name": "Pyr_2m_ch1", "dimension_value": [2, 1]},
        {"raw_name": "Pyr_2m_ch2", "dimension_value": [2, 2]},
        {"raw_name": "Pyr_10m_ch1", "dimension_value": [10, 1]},
        {"raw_name": "Pyr_10m_ch2", "dimension_value": [10, 2]}
      ],
      "standard_name": "surface_downwelling_shortwave_flux_in_air",
      "units": "W m-2"
    }
  ],
  "platform_type": "fixed",   // "fixed" | "mobile" — "mobile" drops lat/lon/elevation
                              // from deployments below (platform_name becomes required
                              // instead) and requires variables mapping standard_name
                              // "latitude"/"longitude", since position then comes from
                              // the data itself, not a fixed point
  "deployments": [
    {
      "start": "2020-01-01T00:00:00Z",
      "end": null,           // null = open-ended; only the LAST deployment may use
                              // null, earlier ones need an explicit ISO end timestamp
      "lat": 78.0,
      "lon": 15.0,
      "elevation": 10
    }
  ],
  "metadata": {
    "title": "UNIS AGF Daudmannsodden AWS",
    "description": "Fixed automatic weather station at Daudmannsodden (Isfjord, Svalbard) recording wind, air pressure, humidity, and temperature with a period of 10min",
    "summary": "",
    "keywords": "",
    "keywords_vocabulary": "",
    "license": "https://spdx.org/licenses/CC-BY-4.0",
    "creator_type": "institution",  // not schema-enforced, but per the ACDD convention
                                     // this field follows: "person" | "group" |
                                     // "institution" | "position"
    "creator_name": "The University Center in Svalbard",
    "creator_institution": "The University Center in Svalbard",
    "creator_email": "post@unis.no",
    "project": "IWIN",
    "institution": "The University Centre in Svalbard (UNIS)",
    "contact_person": "Marius Jonassen (mariusj@unis.no)",
    "department": "Arctic Geophysics",
    "Conventions": "CF-1.10"
  },
  "output": {
    "file_naming": "{station}_{table}_{yyyy}-{mm}.nc",
    "publish": false   // true exposes this dataset via the publish endpoint's
                        // monthly-NetCDF generation (see publish_endpoint.md);
                        // false just makes it browsable/downloadable as normal
  }
}
```

## Adapting it

1. Rename `id` to match this config's filename (`<id>.json`) — required for
   `FolderConfigProvider` to resolve it.
2. Point `source_config.file_pattern`/`table_name` at your station's real TOA5 file and
   table name (see [config_format.md](config_format.md#source_config-loggernet) — the
   pattern must match the *live* file only, not the archived rollover).
3. Replace every `raw_name` with your station's actual column names, and drop whichever
   of the three `variables[]` shapes you don't need — a station with no multi-height
   sensors just skips the `extra_dimension` entries entirely.
4. Set real `deployments` coordinates (and add more entries if the station has moved).
5. Fill in the metadata values for your own station, keeping every key listed above.

See [adding_a_dataset.md](adding_a_dataset.md) for the end-to-end steps (this template
covers step-equivalent config authoring; that doc covers wiring a new source in).
