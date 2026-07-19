from __future__ import annotations

from unittest.mock import patch

import pytest
import xarray as xr
from fastapi.testclient import TestClient

from open_csi_publisher.api.opendap import PortalDatasetProvider, build_opendap_app
from open_csi_publisher.core import builder as builder_module

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


def test_get_dataset_returns_real_xarray_dataset_for_public_id(provider):
    ds = provider.get_dataset("hanna_resvoll_10min")
    assert isinstance(ds, xr.Dataset)
    assert "air_temperature" in ds.data_vars


def test_get_dataset_returns_none_for_restricted_id(provider):
    assert provider.get_dataset("restricted_station") is None


def test_get_dataset_returns_none_for_unknown_id(provider):
    assert provider.get_dataset("does_not_exist") is None


def test_get_dataset_is_cached_within_ttl(provider):
    with patch.object(builder_module, "build_dataset", wraps=builder_module.build_dataset) as spy:
        first = provider.get_dataset("hanna_resvoll_10min")
        second = provider.get_dataset("hanna_resvoll_10min")
    assert spy.call_count == 1
    assert first is second


# --- HTTP-level: real OPeNDAP responses via TestClient -------------------------


@pytest.fixture
def opendap_client(locations, session_factory):
    app = build_opendap_app(session_factory=session_factory, locations=locations)
    return TestClient(app)


def test_datasets_listing_excludes_restricted(opendap_client):
    response = opendap_client.get("/datasets")
    assert response.status_code == 200
    assert "restricted_station" not in response.json()


def test_dds_response_contains_known_variable(opendap_client):
    response = opendap_client.get("/datasets/hanna_resvoll_10min/opendap.dds")
    assert response.status_code == 200
    assert "air_temperature" in response.text


def test_das_response_200(opendap_client):
    response = opendap_client.get("/datasets/hanna_resvoll_10min/opendap.das")
    assert response.status_code == 200


def test_unknown_dataset_404(opendap_client):
    assert opendap_client.get("/datasets/does_not_exist/opendap.dds").status_code == 404


def test_restricted_dataset_404(opendap_client):
    assert opendap_client.get("/datasets/restricted_station/opendap.dds").status_code == 404
