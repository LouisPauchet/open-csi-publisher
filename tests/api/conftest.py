from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from open_csi_publisher.providers.config.folder import FolderConfigProvider
from open_csi_publisher.sources import DatasetLocation
from open_csi_publisher.state.models import Base


@pytest.fixture
def locations(sample_config_dir, fixture_config_dir):
    """The 3 real sample datasets plus the test-only restricted fixture, combined
    into one DatasetLocation list — used across the listing service, JSON route,
    HTML page, and app-factory tests so restricted-exclusion and the
    arbitrary-metadata filter always have something real to exercise."""
    real_provider = FolderConfigProvider(sample_config_dir)
    fixture_provider = FolderConfigProvider(fixture_config_dir)
    return [
        DatasetLocation("real", ds_id, real_provider, None)
        for ds_id in real_provider.list_dataset_ids()
    ] + [
        DatasetLocation("fixtures", ds_id, fixture_provider, None)
        for ds_id in fixture_provider.list_dataset_ids()
    ]


@pytest.fixture
def session_factory():
    """A fresh in-memory-sqlite session factory, for overriding get_db_session in
    router/app tests (TestClient requests run outside the test's own db_session
    fixture, so they need their own factory rather than a single Session).

    StaticPool + check_same_thread=False: TestClient dispatches each request to a
    worker thread (via anyio.to_thread.run_sync); SQLAlchemy's default pool for
    sqlite:///:memory: hands each thread its own connection, i.e. its own separate
    empty in-memory database ("no such table" even though create_all ran). A
    single shared connection is required for an in-memory DB to actually be
    visible across threads.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
