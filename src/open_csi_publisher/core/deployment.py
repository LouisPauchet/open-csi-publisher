from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from open_csi_publisher.core.config_schema import DatasetConfig, Deployment

_OPEN_ENDED_SENTINEL = pd.Timestamp.max


def apply_deployment_metadata(mapped: xr.Dataset, config: DatasetConfig) -> xr.Dataset:
    """Resolve per-timestep deployment metadata against the (already sorted,
    non-overlapping) deployments list. `fixed` resolves station position;
    `mobile` leaves position alone (it's data, mapped straight from the file
    per §4.2) and instead attaches which platform was in use.
    """
    if config.platform_type == "fixed":
        return _apply_fixed(mapped, config.deployments)
    return _apply_mobile(mapped, config.deployments)


def _window_mask(times: pd.DatetimeIndex, dep: Deployment) -> np.ndarray:
    end = pd.Timestamp(dep.end) if dep.end is not None else _OPEN_ENDED_SENTINEL
    return (times >= pd.Timestamp(dep.start)) & (times < end)


def _apply_fixed(ds: xr.Dataset, deployments: list[Deployment]) -> xr.Dataset:
    times = pd.DatetimeIndex(ds["time"].values)
    lat = np.full(len(times), np.nan)
    lon = np.full(len(times), np.nan)
    elevation = np.full(len(times), np.nan)

    for dep in deployments:
        mask = _window_mask(times, dep)
        lat[mask] = dep.lat
        lon[mask] = dep.lon
        if dep.elevation is not None:
            elevation[mask] = dep.elevation

    ds = ds.assign_coords(
        latitude=("time", lat), longitude=("time", lon), elevation=("time", elevation)
    )
    ds["latitude"].attrs.update(standard_name="latitude", units="degrees_north")
    ds["longitude"].attrs.update(standard_name="longitude", units="degrees_east")
    ds["elevation"].attrs.update(standard_name="height", units="m", positive="up")
    return ds


def _apply_mobile(ds: xr.Dataset, deployments: list[Deployment]) -> xr.Dataset:
    times = pd.DatetimeIndex(ds["time"].values)
    platform = np.full(len(times), None, dtype=object)

    for dep in deployments:
        mask = _window_mask(times, dep)
        platform[mask] = dep.platform_name

    return ds.assign_coords(platform=("time", platform))
