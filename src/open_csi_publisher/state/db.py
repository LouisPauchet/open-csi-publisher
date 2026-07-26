from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def get_engine(database_url: str) -> Engine:
    return create_engine(database_url, future=True)


def run_migrations(database_url: str, base_dir: str = ".") -> None:
    """Brings the database schema up to the latest Alembic revision, creating it
    from scratch if it doesn't exist yet — the migration-managed replacement for
    the old `Base.metadata.create_all()`. `alembic.ini` is resolved relative to
    `base_dir`, the same convention `settings.sources_file`/`branding_file` use,
    since the installed package (no `src/` layout) can't locate it relative to
    this module's own path.
    """
    cfg = Config(str(Path(base_dir) / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
