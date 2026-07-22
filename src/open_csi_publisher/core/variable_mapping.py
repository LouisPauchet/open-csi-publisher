from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
import xarray as xr
from loguru import logger

from open_csi_publisher.core.config_schema import VariableSpec


def apply_variable_spec(raw: xr.Dataset, variables: Sequence[VariableSpec]) -> xr.Dataset:
    """Rename raw columns to their canonical output name and stack extra_dimension
    member columns into one variable along a new dimension. A variable whose raw
    column(s) aren't present at all in `raw` is silently dropped (not an error) —
    e.g. querying a time window predating a sensor's installation.
    """
    data_vars: dict[str, xr.DataArray] = {}
    data_quality_warnings: list[str] = []
    for spec in variables:
        mapped = _stack_extra_dimension(raw, spec) if spec.extra_dimension else _coalesce_aliases(raw, spec)
        if mapped is not None:
            mapped, warning = _coerce_numeric(mapped, spec)
            if warning is not None:
                data_quality_warnings.append(warning)
            data_vars[spec.canonical_name] = mapped

    ds = xr.Dataset(data_vars, coords={"time": raw["time"]})
    if data_quality_warnings:
        ds.attrs["data_quality_warnings"] = "; ".join(data_quality_warnings)
    return ds


def _coerce_numeric(array: xr.DataArray, spec: VariableSpec) -> tuple[xr.DataArray, str | None]:
    """A `dtype: "numeric"` variable's raw values are, per the config schema,
    supposed to already be numbers — but a source can report the same
    quantity using a mix of JSON types across points (observed with
    ThingsBoard's timeseries API, which returns each point in whatever type
    it was originally stored as). Left alone, that mix becomes an object-dtype
    array that build_dataset() happily produces but to_netcdf()/OPeNDAP fail
    to serialize much later, far from the actual cause. Coercing here recovers
    every numeric-looking string losslessly and silently (not a data-quality
    issue, just a source type quirk); anything genuinely unparseable becomes
    NaN (this pipeline's standard "missing data, not an error" convention)
    and is reported back to the caller so it ends up in the built dataset's
    `data_quality_warnings` global attribute, not just the application log —
    a data consumer reading the file has no access to the server's logs.
    """
    if spec.dtype != "numeric" or array.dtype != object:
        return array, None

    coerced = pd.to_numeric(array.values, errors="coerce")
    newly_nan = pd.isna(coerced) & ~pd.isna(array.values)
    warning = None
    if newly_nan.any():
        bad_values = list(np.unique(array.values[newly_nan]))
        count = int(newly_nan.sum())
        warning = (
            f"{spec.canonical_name}: {count} value(s) could not be parsed as numeric "
            f"and were set to NaN (examples: {bad_values})"
        )
        logger.warning(warning)
    return array.copy(data=coerced.astype("float64")), warning


def _coalesce_aliases(raw: xr.Dataset, spec: VariableSpec) -> xr.DataArray | None:
    """A reconciled fileset spanning a column rename (raw_name -> old_names, or
    vice versa across a sensor swap) can have more than one of the aliased raw
    columns present simultaneously, each populated for a disjoint time range
    (NaN elsewhere from the fileset's outer join). Coalesce them into one series
    rather than just picking the first alias found.
    """
    candidates = [name for name in spec.all_raw_names() if name in raw.data_vars]
    if not candidates:
        return None

    result = raw[candidates[0]]
    for name in candidates[1:]:
        result = result.combine_first(raw[name])

    result = result.rename(spec.canonical_name)
    result.attrs = dict(raw[candidates[0]].attrs)
    if spec.units:
        result.attrs["units"] = spec.units
    if spec.standard_name:
        result.attrs["standard_name"] = spec.standard_name
    return result


def _stack_extra_dimension(raw: xr.Dataset, spec: VariableSpec) -> xr.DataArray | None:
    """Stack member columns along one or more `extra_dimension` coordinates.

    Uses a `pd.MultiIndex` (one level per declared dimension) plus
    `xr.DataArray.unstack` rather than a plain `xr.concat`, so N declared
    dimensions produce a genuine N-D array: a height x channel spec, for
    example, ends up with two independent dims, not one flattened one.
    `unstack` also fills in any combination no member declared at all as
    NaN automatically (implicit outer join across the dimensions), and its
    per-dimension coordinate values naturally come out as object dtype when
    any `dimension_value` is a string (e.g. named statistics like "average"/
    "maximum" rather than a numeric height/channel) — required because
    opendap-protocol's generic array encoder writes a fixed-width numpy
    string array's raw bytes straight onto the wire with no per-element
    DAP2 length prefix, producing a DATADDS response DAP clients reject as
    malformed ("NetCDF: Malformed or inaccessible DAP2 DATADDS or DAP4 DAP
    response"). `unstack` sorts each dimension's coordinate ascending,
    which does not match declaration order in general, so the result is
    reindexed back to first-declared order per dimension afterward.
    """
    assert spec.extra_dimension is not None
    if not any(member.raw_name in raw.data_vars for member in spec.members):
        return None

    member_arrays = []
    dim_tuples: list[tuple] = []
    for member in spec.members:
        if member.raw_name in raw.data_vars:
            member_arrays.append(raw[member.raw_name])
        else:
            member_arrays.append(
                xr.DataArray(np.full(raw.sizes["time"], np.nan), dims="time")
            )
        value = member.dimension_value
        dim_tuples.append(tuple(value) if isinstance(value, list) else (value,))

    dim_names = [d.name for d in spec.extra_dimension]
    stacked = xr.concat(member_arrays, dim="_member")
    multi_index = pd.MultiIndex.from_tuples(dim_tuples, names=dim_names)
    stacked = stacked.assign_coords(xr.Coordinates.from_pandas_multiindex(multi_index, "_member"))
    stacked = stacked.unstack("_member")

    declaration_order = {
        name: list(dict.fromkeys(values))
        for name, values in zip(dim_names, zip(*dim_tuples))
    }
    stacked = stacked.reindex(declaration_order)

    stacked = stacked.rename(spec.canonical_name)
    stacked.attrs = {}
    if spec.standard_name:
        stacked.attrs["standard_name"] = spec.standard_name
    if spec.units:
        stacked.attrs["units"] = spec.units
    for dim in spec.extra_dimension:
        stacked[dim.name].attrs["units"] = dim.units
    return stacked
