from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import xarray as xr
from fastapi.testclient import TestClient

from open_csi_publisher import settings as settings_module
from open_csi_publisher.api.opendap import PortalDatasetProvider, build_opendap_app
from open_csi_publisher.core import builder as builder_module
from open_csi_publisher.core.models import FileRecord
from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.sources import DatasetLocation

from ..conftest import requires_mount

# --- unit-level: PortalDatasetProvider hooks, no HTTP -------------------------


@pytest.fixture
def provider(locations, session_factory):
    return PortalDatasetProvider(session_factory=session_factory, locations=locations)


def test_get_datasets_lists_only_public_datasets(provider):
    ids = provider.get_datasets()
    assert "restricted_station" not in ids
    assert "isfjord_radio_solar_park_measurements3" in ids
    assert "hanna_resvoll_10min" in ids
    assert "kapp_thordsen_10minute" in ids


@requires_mount
def test_get_dataset_returns_real_xarray_dataset_for_public_id(provider):
    ds = provider.get_dataset("hanna_resvoll_10min")
    assert isinstance(ds, xr.Dataset)
    assert "air_temperature" in ds.data_vars


def test_get_dataset_returns_none_for_restricted_id(provider):
    assert provider.get_dataset("restricted_station") is None


def test_get_dataset_returns_none_for_unknown_id(provider):
    assert provider.get_dataset("does_not_exist") is None


@requires_mount
def test_get_dataset_is_cached_within_ttl(provider):
    with patch.object(builder_module, "build_dataset", wraps=builder_module.build_dataset) as spy:
        first = provider.get_dataset("hanna_resvoll_10min")
        second = provider.get_dataset("hanna_resvoll_10min")
    assert spy.call_count == 1
    assert first is second


# --- size-cap exclusion (Fix F): OPeNDAP needs one whole dataset cached in
# memory to support arbitrary DAP2 slicing, fundamentally incompatible with a
# station too large to ever fully build -----------------------------------------


class _OversizedDataProvider:
    """get_file_index() reports a dataset far larger than any reasonable cap;
    read_range() must never be reached if size-limit exclusion works."""

    def get_file_index(self, source_config, previous=()):
        return [
            FileRecord(
                file_name="huge.dat",
                file_role="live",
                size=100 * 1024**3,
                time_start=datetime(2020, 1, 1),
                time_end=datetime(2020, 1, 2),
                variables=["air_pressure"],
                status="active",
            )
        ]

    def read_range(self, *args, **kwargs):
        raise AssertionError("read_range should never be called for an oversized dataset")


class _FailingReadRangeDataProvider:
    """A working file index, but read_range() always fails — simulates a real
    build failure (ThingsBoard error, stalled mount, whatever) reaching
    PortalDatasetProvider.get_dataset(), which the main app's exception
    handlers (Fix A) can't help with since /opendap is a separately mounted
    ASGI app."""

    def get_file_index(self, source_config, previous=()):
        return [
            FileRecord(
                file_name="live.dat",
                file_role="live",
                size=10,
                time_start=datetime(2020, 1, 1),
                time_end=datetime(2020, 1, 2),
                variables=["air_pressure"],
                status="active",
            )
        ]

    def read_range(self, *args, **kwargs):
        raise ValueError("simulated build failure")


@pytest.fixture
def oversized_location(sample_config_dir):
    config_provider = FolderConfigProvider(sample_config_dir)
    return DatasetLocation("real", "kapp_thordsen_10minute", config_provider, _OversizedDataProvider())


@pytest.fixture
def failing_location(sample_config_dir):
    config_provider = FolderConfigProvider(sample_config_dir)
    return DatasetLocation("real", "kapp_thordsen_10minute", config_provider, _FailingReadRangeDataProvider())


def test_get_datasets_excludes_a_dataset_whose_total_size_exceeds_the_cap(
    session_factory, oversized_location, monkeypatch
):
    monkeypatch.setattr(settings_module.settings, "max_dataset_build_bytes", 1024**3)  # 1 GB
    provider = PortalDatasetProvider(session_factory=session_factory, locations=[oversized_location])
    assert provider.get_datasets() == []


def test_get_datasets_exclusion_logs_a_warning(session_factory, oversized_location, monkeypatch, caplog):
    monkeypatch.setattr(settings_module.settings, "max_dataset_build_bytes", 1024**3)
    provider = PortalDatasetProvider(session_factory=session_factory, locations=[oversized_location])
    provider.get_datasets()
    assert "kapp_thordsen_10minute" in caplog.text
    assert "opendap" in caplog.text.lower()


def test_get_dataset_returns_none_for_a_dataset_over_the_cap(session_factory, oversized_location, monkeypatch):
    monkeypatch.setattr(settings_module.settings, "max_dataset_build_bytes", 1024**3)
    provider = PortalDatasetProvider(session_factory=session_factory, locations=[oversized_location])
    assert provider.get_dataset("kapp_thordsen_10minute") is None


def test_get_datasets_includes_dataset_comfortably_under_the_cap(session_factory, oversized_location, monkeypatch):
    monkeypatch.setattr(settings_module.settings, "max_dataset_build_bytes", 1024**4)  # 1 TB
    provider = PortalDatasetProvider(session_factory=session_factory, locations=[oversized_location])
    assert provider.get_datasets() == ["kapp_thordsen_10minute"]


def test_get_dataset_returns_none_and_logs_when_build_fails(session_factory, failing_location, caplog):
    provider = PortalDatasetProvider(session_factory=session_factory, locations=[failing_location])
    assert provider.get_dataset("kapp_thordsen_10minute") is None
    assert "kapp_thordsen_10minute" in caplog.text


def test_size_limit_verdict_is_cached_not_recomputed_every_call(
    session_factory, oversized_location, monkeypatch, caplog
):
    monkeypatch.setattr(settings_module.settings, "max_dataset_build_bytes", 1024**3)
    provider = PortalDatasetProvider(session_factory=session_factory, locations=[oversized_location])

    provider.get_datasets()
    assert caplog.text.count("excluding dataset") == 1
    caplog.clear()

    provider.get_datasets()  # same provider instance: size_limit_cache should short-circuit
    assert "excluding dataset" not in caplog.text


_GENERIC_CSV_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "generic_csv"


def test_size_limit_not_checked_for_non_loggernet_sources(session_factory, monkeypatch):
    # generic_csv is always exactly one file — the size cap (scoped to
    # loggernet in core/builder.py::_check_size_cap) doesn't apply here
    # either; an absurdly tiny limit must not exclude it.
    monkeypatch.setattr(settings_module.settings, "max_dataset_build_bytes", 1)
    from open_csi_publisher.providers.data.generic_csv.provider import GenericCsvDataProvider

    config_provider = FolderConfigProvider(_GENERIC_CSV_FIXTURE_ROOT / "configs")
    data_provider = GenericCsvDataProvider(_GENERIC_CSV_FIXTURE_ROOT / "data")
    location = DatasetLocation("generic", "generic_csv_demo", config_provider, data_provider)

    provider = PortalDatasetProvider(session_factory=session_factory, locations=[location])
    assert provider.get_datasets() == ["generic_csv_demo"]


# --- HTTP-level: real OPeNDAP responses via TestClient -------------------------


@pytest.fixture
def opendap_client(locations, session_factory):
    app = build_opendap_app(session_factory=session_factory, locations=locations)
    return TestClient(app)


def test_datasets_listing_excludes_restricted(opendap_client):
    response = opendap_client.get("/datasets")
    assert response.status_code == 200
    assert "restricted_station" not in response.json()


@requires_mount
def test_dds_response_contains_known_variable(opendap_client):
    response = opendap_client.get("/datasets/hanna_resvoll_10min/opendap.dds")
    assert response.status_code == 200
    assert "air_temperature" in response.text


@requires_mount
def test_das_response_200(opendap_client):
    response = opendap_client.get("/datasets/hanna_resvoll_10min/opendap.das")
    assert response.status_code == 200


def test_unknown_dataset_404(opendap_client):
    assert opendap_client.get("/datasets/does_not_exist/opendap.dds").status_code == 404


def test_restricted_dataset_404(opendap_client):
    assert opendap_client.get("/datasets/restricted_station/opendap.dds").status_code == 404


def _parse_dap2_string_array(dods_bytes: bytes) -> list[str]:
    """Decode a DAP2 String-array .dods payload per the spec (and matching
    pydap's reference encoder): a single 4-byte element count, then per
    element a 4-byte length prefix, the raw bytes, and zero-padding up to
    the next 4-byte boundary."""
    body = dods_bytes[dods_bytes.index(b"Data:\r\n") + len(b"Data:\r\n") :]
    count = int.from_bytes(body[0:4], "big")
    pos = 4
    values = []
    for _ in range(count):
        length = int.from_bytes(body[pos : pos + 4], "big")
        pos += 4
        values.append(body[pos : pos + length].decode("ascii"))
        pos += length + (-length % 4)
    return values


@requires_mount
def test_dods_response_correctly_encodes_a_string_valued_dimension(opendap_client):
    # Regression test for the "NetCDF: Malformed or inaccessible DAP2
    # DATADDS or DAP4 DAP response" bug: opendap_protocol's generic array
    # encoder mishandles DAP2 String arrays (doubles the length header like
    # a numeric array, then dumps fixed-width bytes with no per-element
    # length prefix). api/opendap.py patches this at import time; this
    # fetches the raw .dods bytes for a string-valued extra_dimension
    # coordinate and decodes them per the actual DAP2 spec to confirm the
    # values round-trip correctly, rather than just checking for a 200.
    response = opendap_client.get(
        "/datasets/string_extra_dimension_station/opendap.dods?statistics"
    )
    assert response.status_code == 200
    assert _parse_dap2_string_array(response.content) == ["average", "maximum"]
