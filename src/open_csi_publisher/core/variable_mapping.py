from __future__ import annotations

from typing import Sequence

import numpy as np
import xarray as xr

from open_csi_publisher.core.config_schema import VariableSpec


def apply_variable_spec(raw: xr.Dataset, variables: Sequence[VariableSpec]) -> xr.Dataset:
    """Rename raw columns to their canonical output name and stack extra_dimension
    member columns into one variable along a new dimension. A variable whose raw
    column(s) aren't present at all in `raw` is silently dropped (not an error) —
    e.g. querying a time window predating a sensor's installation.
    """
    data_vars: dict[str, xr.DataArray] = {}
    for spec in variables:
        mapped = _stack_extra_dimension(raw, spec) if spec.extra_dimension else _coalesce_aliases(raw, spec)
        if mapped is not None:
            data_vars[spec.canonical_name] = mapped

    return xr.Dataset(data_vars, coords={"time": raw["time"]})


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
    assert spec.extra_dimension is not None
    if not any(member.raw_name in raw.data_vars for member in spec.members):
        return None

    member_arrays = []
    dim_values = []
    for member in spec.members:
        if member.raw_name in raw.data_vars:
            member_arrays.append(raw[member.raw_name])
        else:
            member_arrays.append(
                xr.DataArray(np.full(raw.sizes["time"], np.nan), dims="time")
            )
        dim_values.append(member.dimension_value)

    dim_name = spec.extra_dimension.name
    stacked = xr.concat(member_arrays, dim=dim_name)
    # object dtype, not numpy's auto-inferred fixed-width "<U*", when any
    # dimension_value is a string (e.g. named statistics like "average"/
    # "maximum" rather than a numeric height/channel): opendap-protocol's
    # generic array encoder writes a fixed-width numpy string array's raw
    # bytes straight onto the wire with no per-element DAP2 length prefix,
    # producing a DATADDS response DAP clients reject as malformed ("NetCDF:
    # Malformed or inaccessible DAP2 DATADDS or DAP4 DAP response"). Values
    # kept as genuine Python str objects (object dtype) go through a
    # different, correct encoding path — the same one already used for
    # plain string data variables like MetSENS_Status.
    if any(isinstance(value, str) for value in dim_values):
        dim_values = np.array(dim_values, dtype=object)
    stacked = stacked.assign_coords({dim_name: dim_values})
    stacked = stacked.rename(spec.canonical_name)
    stacked.attrs = {}
    if spec.standard_name:
        stacked.attrs["standard_name"] = spec.standard_name
    if spec.units:
        stacked.attrs["units"] = spec.units
    stacked[dim_name].attrs["units"] = spec.extra_dimension.units
    return stacked
