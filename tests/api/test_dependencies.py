from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from open_csi_publisher.api.deps import get_dataset_location, get_dataset_locations, get_db_session
from open_csi_publisher.state import repository
from open_csi_publisher.state.models import Base


def _fake_request_with_fresh_sqlite():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_factory=session_factory)))


def test_get_db_session_yields_a_working_session():
    request = _fake_request_with_fresh_sqlite()
    gen = get_db_session(request)
    session = next(gen)

    assert repository.get_current_config_version(session, "station_a") is None

    gen.close()


def test_get_db_session_commits_on_successful_completion():
    request = _fake_request_with_fresh_sqlite()
    session_factory = request.app.state.session_factory

    gen = get_db_session(request)
    session = next(gen)
    repository.record_config_version(session, "station_a", "hash1", {"id": "station_a"})
    try:
        next(gen)
    except StopIteration:
        pass  # generator completing normally is what triggers the commit

    with session_factory() as fresh_session:
        version = repository.get_current_config_version(fresh_session, "station_a")
        assert version is not None
        assert version.hash == "hash1"


def test_get_dataset_locations_returns_the_real_sample_datasets():
    locations = get_dataset_locations()
    dataset_ids = {loc.dataset_id for loc in locations}
    assert dataset_ids == {
        "isfjord_radio_solar_park_measurements3",
        "kapp_thordsen_10minute",
        "hanna_resvoll_10min",
    }


def test_get_dataset_location_returns_matching_location(locations):
    location = get_dataset_location("hanna_resvoll_10min", locations=locations)
    assert location.dataset_id == "hanna_resvoll_10min"


def test_get_dataset_location_raises_404_for_unknown_id(locations):
    with pytest.raises(HTTPException) as exc_info:
        get_dataset_location("does_not_exist", locations=locations)
    assert exc_info.value.status_code == 404
