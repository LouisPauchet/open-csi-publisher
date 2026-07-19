from __future__ import annotations

import xarray as xr


def render_csv_with_metadata_header(ds: xr.Dataset) -> str:
    """CSV text with the dataset's global attributes (title, institution,
    processing provenance, etc.) as a `#`-commented preamble before the
    ordinary header/data rows — a standard, widely-recognized convention for
    self-describing scientific CSV exports. Read back with
    `pandas.read_csv(path, comment="#")` to skip the preamble automatically.
    """
    header_lines = [f"# {key}: {_flatten(value)}" for key, value in ds.attrs.items()]
    data_csv = ds.to_dataframe().reset_index().to_csv(index=False)
    return "\n".join([*header_lines, "#", data_csv])


def _flatten(value: object) -> str:
    # a stray newline in an attribute value would otherwise produce a
    # non-"#"-prefixed line, breaking the comment convention for readers
    # that only skip lines starting with "#"
    return str(value).replace("\r\n", " ").replace("\n", " ")
