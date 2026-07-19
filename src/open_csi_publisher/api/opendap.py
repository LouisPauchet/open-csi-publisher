from __future__ import annotations

from typing import Any

import xarray as xr
import xpublish
from cachetools import TTLCache
from fastapi import FastAPI
from pydantic import ConfigDict
from xpublish.plugins import hookimpl
from xpublish.plugins.manage import load_default_plugins

from open_csi_publisher.core import builder as builder_module
from open_csi_publisher.core.config_versioning import get_versioned_config
from open_csi_publisher.sources import DatasetLocation


class PortalDatasetProvider(xpublish.Plugin):
    """Serves every *public* configured dataset dynamically via build_dataset().

    Restricted datasets are never registered at all — get_datasets() omits
    them and get_dataset() returns None for them — matching
    implementation_plan.md §8 ("restricted datasets are never registered with
    / served by this handler at all").

    Cached with a short TTL to absorb repeated polling (Grafana, xarray
    clients re-opening the same dataset) without rebuilding on every request.
    Note xpublish-opendap has its own much longer (~27.7h) internal cache for
    the DAP-protocol-converted representation, keyed off calling this hook
    once; this TTL mainly matters for the first OPeNDAP request after a
    restart and for the non-OPeNDAP dataset_info routes, which have no cache
    of their own.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "portal-datasets"
    session_factory: Any
    locations: list[DatasetLocation]
    cache: TTLCache = TTLCache(maxsize=128, ttl=60)

    @hookimpl
    def get_datasets(self) -> list[str]:
        return [loc.dataset_id for loc in self.locations if self._is_public(loc)]

    @hookimpl
    def get_dataset(self, dataset_id: str) -> xr.Dataset | None:
        if dataset_id in self.cache:
            return self.cache[dataset_id]

        location = next((loc for loc in self.locations if loc.dataset_id == dataset_id), None)
        if location is None or not self._is_public(location):
            return None

        with self.session_factory() as session:
            ds = builder_module.build_dataset(
                dataset_id,
                session=session,
                config_provider=location.config_provider,
                data_provider=location.data_provider,
            )
        self.cache[dataset_id] = ds
        return ds

    def _is_public(self, location: DatasetLocation) -> bool:
        with self.session_factory() as session:
            config = get_versioned_config(
                location.dataset_id, session=session, config_provider=location.config_provider
            )
        return config.access == "public"


def build_opendap_app(*, session_factory: Any, locations: list[DatasetLocation]) -> FastAPI:
    """A standalone xpublish FastAPI app serving OPeNDAP (plus xpublish's own
    dataset_info/module_version/plugin_info routes) for every public dataset.
    Mounted under /opendap by create_app(); URLs end up
    /opendap/datasets/{dataset_id}/opendap.dds (etc.) — the doubled "opendap"
    segment is accepted (implementation_plan.md's OPeNDAP design notes): OPeNDAP
    clients are always handed a full base URL to open, never expected to guess
    a path convention.

    Known client-interop caveat, confirmed by hand against a real running
    server (not just TestClient): .dds/.das responses and the raw .dods byte
    stream are protocol-correct and complete — verified independently via
    curl and Python's `requests` library, including the exact dds->das->dods
    request sequence a real client makes, and via this project's own
    TestClient-based tests. However, `xr.open_dataset(url, engine="pydap")`
    (the `pydap` package specifically, not OPeNDAP in general) reproducibly
    raised `ChunkedEncodingError: Response ended prematurely` when actually
    reading variable data, on every attempt, regardless of dataset size or
    the dap2:// vs http:// URL scheme pydap itself suggests. Root cause not
    isolated (time did not permit going further than ruling out payload
    truncation and Range-header usage on pydap's side) — likely an
    interaction between pydap's own lazy/streaming array-fetching and this
    server's chunked-transfer StreamingResponse. Follow-up: try a
    non-chunked (Content-Length-bearing) response, or test against a
    non-pydap DAP2 client (e.g. plain curl-based tooling, or netCDF4's own
    OPeNDAP support) to confirm the scope of the incompatibility.
    """
    plugins = load_default_plugins()
    plugins["portal-datasets"] = PortalDatasetProvider(
        session_factory=session_factory, locations=locations
    )
    rest = xpublish.Rest({}, plugins=plugins)
    return rest.app
