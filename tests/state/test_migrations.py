from __future__ import annotations

from sqlalchemy import create_engine, inspect

from open_csi_publisher.state.db import run_migrations
from open_csi_publisher.state.models import Base

from ..conftest import REPO_ROOT


def _schema_snapshot(engine):
    inspector = inspect(engine)
    return {
        table: {col["name"] for col in inspector.get_columns(table)}
        for table in sorted(inspector.get_table_names())
        if table != "alembic_version"
    }


def test_run_migrations_matches_create_all_schema(tmp_path):
    migrated_db = tmp_path / "migrated.db"
    run_migrations(f"sqlite:///{migrated_db}", base_dir=str(REPO_ROOT))
    migrated_engine = create_engine(f"sqlite:///{migrated_db}")

    created_db = tmp_path / "created.db"
    created_engine = create_engine(f"sqlite:///{created_db}")
    Base.metadata.create_all(created_engine)

    assert _schema_snapshot(migrated_engine) == _schema_snapshot(created_engine)


def test_run_migrations_is_idempotent(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'state.db'}"

    run_migrations(database_url, base_dir=str(REPO_ROOT))
    run_migrations(database_url, base_dir=str(REPO_ROOT))  # must not raise
