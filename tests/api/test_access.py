from __future__ import annotations

import copy

import pytest
from fastapi import HTTPException

from open_csi_publisher.api.access import is_visible, require_visible
from open_csi_publisher.api.auth import User
from open_csi_publisher.core.config_schema import DatasetConfig

BASE_CONFIG = {
    "id": "station_a",
    "source_type": "loggernet",
    "access": "public",
    "source_config": {"file_pattern": "station_a/Table.dat"},
    "variables": [{"raw_name": "AirT_C", "standard_name": "air_temperature"}],
    "platform_type": "fixed",
    "deployments": [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6}],
    "metadata": {"title": "Station A"},
    "output": {"file_naming": "{station}.nc"},
}


def _config(access: str) -> DatasetConfig:
    doc = copy.deepcopy(BASE_CONFIG)
    doc["access"] = access
    return DatasetConfig.model_validate(doc)


@pytest.mark.parametrize(
    "access,user,expected",
    [
        ("public", None, True),
        ("public", User(subject="u"), True),
        ("restricted", None, False),
        ("restricted", User(subject="u"), True),
    ],
)
def test_is_visible(access, user, expected):
    assert is_visible(_config(access), user) is expected


def test_require_visible_passes_silently_when_visible():
    require_visible(_config("public"), None)  # no exception


def test_require_visible_raises_404_not_403_for_restricted_anonymous():
    with pytest.raises(HTTPException) as exc_info:
        require_visible(_config("restricted"), None)
    assert exc_info.value.status_code == 404


def test_require_visible_passes_for_restricted_authenticated_user():
    require_visible(_config("restricted"), User(subject="u"))  # no exception
