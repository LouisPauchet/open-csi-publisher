from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from open_csi_publisher.state.models import Base


def get_engine(database_url: str) -> Engine:
    return create_engine(database_url, future=True)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
