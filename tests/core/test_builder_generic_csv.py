from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from open_csi_publisher.core.builder import build_dataset
from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.providers.data.generic_csv.provider import GenericCsvDataProvider

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "generic_csv"


@pytest.fixture
def config_provider():
    return FolderConfigProvider(FIXTURE_ROOT / "configs")


@pytest.fixture
def data_provider():
    return GenericCsvDataProvider(FIXTURE_ROOT / "data")


def test_build_dataset_end_to_end_against_a_wholly_different_source_type(
    db_session, config_provider, data_provider
):
    """The real point of the second-source-type phase: build_dataset() (core/
    builder.py) never imports or references LoggerNet-anything, so it must
    work identically against a structurally unrelated source — a single flat
    CSV file, mtime-based change detection, no fileset reconciliation at
    all — proving the two plugin points (ConfigProvider/DataProvider) are
    genuinely independent of the core pipeline, per implementation_plan.md §13.
    """
    ds = build_dataset(
        "generic_csv_demo",
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )

    assert ds.sizes["time"] == 5
    assert "air_temperature" in ds.data_vars
    assert "relative_humidity" in ds.data_vars
    assert float(ds["air_temperature"].isel(time=0).values) == 1.0

    # fixed-platform deployment resolution works identically regardless of
    # source type — it operates on the mapped xr.Dataset, not raw provider output
    assert (ds["latitude"].values == 60.0).all()
    assert (ds["longitude"].values == 10.0).all()

    assert ds.attrs["title"] == "Generic CSV Demo Station"


def test_build_dataset_time_window_and_variable_filter(db_session, config_provider, data_provider):
    ds = build_dataset(
        "generic_csv_demo",
        start=datetime(2026, 1, 1, 0, 10, 0),
        end=datetime(2026, 1, 1, 0, 30, 0),
        variables=["air_temperature"],
        session=db_session,
        config_provider=config_provider,
        data_provider=data_provider,
    )
    assert list(ds.data_vars) == ["air_temperature"]
    assert ds.sizes["time"] == 3
