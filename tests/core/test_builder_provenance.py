from __future__ import annotations

from pathlib import Path

import pytest

from open_csi_publisher.core.builder import build_dataset
from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.providers.data.generic_csv.provider import GenericCsvDataProvider
from open_csi_publisher.state import repository

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "generic_csv"


@pytest.fixture
def config_provider():
    return FolderConfigProvider(FIXTURE_ROOT / "configs")


@pytest.fixture
def data_provider():
    return GenericCsvDataProvider(FIXTURE_ROOT / "data")


def test_build_dataset_always_attaches_provenance_attrs(db_session, config_provider, data_provider):
    ds = build_dataset(
        "generic_csv_demo", session=db_session, config_provider=config_provider, data_provider=data_provider
    )

    assert ds.attrs["processing_software_version"]
    assert ds.attrs["config_hash"]
    assert ds.attrs["config_version_timestamp"]
    assert "history" in ds.attrs
    assert ds.attrs["processing_software_version"] in ds.attrs["history"]
    assert "generic_csv_demo" in ds.attrs["history"]


def test_build_dataset_uses_unis_id_not_id_for_the_internal_slug(
    db_session, config_provider, data_provider
):
    # ACDD reserves the "id" (+ "naming_authority") global attributes for
    # whichever downstream system formally publishes/archives this data
    # (assigns its own citable identifier) — our own internal dataset slug
    # must not claim that name, or it'd collide when a publisher sets its
    # own "id" on top of a file we produced.
    ds = build_dataset(
        "generic_csv_demo", session=db_session, config_provider=config_provider, data_provider=data_provider
    )
    assert ds.attrs["unis_id"] == "generic_csv_demo"
    assert "id" not in ds.attrs


def test_provenance_config_hash_matches_the_recorded_config_version(
    db_session, config_provider, data_provider
):
    ds = build_dataset(
        "generic_csv_demo", session=db_session, config_provider=config_provider, data_provider=data_provider
    )
    recorded = repository.get_current_config_version(db_session, "generic_csv_demo")
    assert ds.attrs["config_hash"] == recorded.hash
    assert ds.attrs["config_version_timestamp"] == recorded.created_at.isoformat()


def test_provenance_software_version_matches_installed_package_version(
    db_session, config_provider, data_provider
):
    from importlib.metadata import version

    ds = build_dataset(
        "generic_csv_demo", session=db_session, config_provider=config_provider, data_provider=data_provider
    )
    assert ds.attrs["processing_software_version"] == version("open-csi-publisher")
