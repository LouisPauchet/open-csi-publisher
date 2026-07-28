from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import xarray as xr


def render_csv_with_metadata_header(ds: xr.Dataset) -> str:
    """CSV text with the dataset's global attributes (title, institution,
    processing provenance, etc.) as a `#`-commented preamble before the
    ordinary header/data rows — a standard, widely-recognized convention for
    self-describing scientific CSV exports. Read back with
    `pandas.read_csv(path, comment="#")` to skip the preamble automatically.
    """
    header_lines = [f"# {key}: {_flatten(value)}" for key, value in ds.attrs.items()]
    data_csv = to_wide_dataframe(ds).to_csv(index=False)
    return "\n".join([*header_lines, "#", data_csv])


def to_wide_dataframe(ds: xr.Dataset) -> pd.DataFrame:
    """Flatten `ds` to a wide-format DataFrame: one row per `time`, with any
    variable that has extra dimensions beyond `time` (an `extra_dimension`
    group, e.g. air_temperature at several heights) exploded into one column
    per dimension-value combination instead of `xr.Dataset.to_dataframe()`'s
    long format (one row per (time, <dim>) combination, duplicating every
    other variable's value once per dimension value).
    """
    columns: dict[str, np.ndarray] = {}
    for name, da in ds.data_vars.items():
        extra_dims = [d for d in da.dims if d != "time"]
        if not extra_dims:
            columns[name] = da.values
            continue

        coord_values = [da[d].values for d in extra_dims]
        units = [da[d].attrs.get("units") for d in extra_dims]
        for combo in itertools.product(*(range(len(v)) for v in coord_values)):
            selector = {d: coord_values[i][idx] for i, (d, idx) in enumerate(zip(extra_dims, combo))}
            segment = "_".join(
                _format_dim_value(coord_values[i][idx], units[i]) for i, idx in enumerate(combo)
            )
            columns[f"{name}_{segment}"] = da.sel(selector).values

    return pd.DataFrame(columns, index=pd.Index(ds["time"].values, name="time")).reset_index()


def _format_dim_value(value: object, units: str | None) -> str:
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        value = int(value)
    text = str(value).strip().replace(" ", "_")
    if units and isinstance(value, (int, float, np.integer, np.floating)):
        return f"{text}{units}"
    return text


def _flatten(value: object) -> str:
    # a stray newline in an attribute value would otherwise produce a
    # non-"#"-prefixed line, breaking the comment convention for readers
    # that only skip lines starting with "#"
    return str(value).replace("\r\n", " ").replace("\n", " ")
