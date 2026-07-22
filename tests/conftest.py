from __future__ import annotations

from pathlib import Path

import pytest
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parent.parent
MOUNT_ROOT = REPO_ROOT / "mount" / "loggernet-test-server"
SAMPLE_CONFIG_DIR = REPO_ROOT / "sample_configs"
FIXTURE_CONFIG_DIR = Path(__file__).resolve().parent / "fixtures" / "configs"

requires_mount = pytest.mark.skipif(
    not MOUNT_ROOT.exists(),
    reason="real sample data not present under mount/loggernet-test-server/",
)


@pytest.fixture
def mount_root() -> Path:
    return MOUNT_ROOT


@pytest.fixture
def sample_config_dir() -> Path:
    return SAMPLE_CONFIG_DIR


@pytest.fixture
def fixture_config_dir() -> Path:
    return FIXTURE_CONFIG_DIR


@pytest.fixture
def sqlite_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    from open_csi_publisher.state.models import Base

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(sqlite_engine):
    with Session(sqlite_engine) as session:
        yield session


@pytest.fixture
def caplog(caplog):
    """Route loguru's output into pytest's caplog. loguru doesn't propagate into
    the stdlib `logging` hierarchy on its own, so without this, `caplog.text`/
    `caplog.records` would never see anything logged via `from loguru import
    logger`, regardless of level."""
    handler_id = logger.add(caplog.handler, format="{message}")
    yield caplog
    logger.remove(handler_id)
