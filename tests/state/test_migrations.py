from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from open_csi_publisher.state.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_migrations_produce_the_schema_the_models_declare(tmp_path):
    """Guards model/migration drift: file_index.size was BigInteger in the
    model but Integer in the baseline migration, so Postgres rejected
    ThingsBoard's epoch-millisecond change token ("integer out of range") while
    sqlite-backed tests (create_all from the models) never noticed."""
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()

    assert diff == []
