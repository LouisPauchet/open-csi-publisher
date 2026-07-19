from __future__ import annotations

from open_csi_publisher.api.auth import User
from open_csi_publisher.api.services import list_visible_datasets

ANONYMOUS = None
LOGGED_IN = User(subject="test-user")


def _ids(result) -> set[str]:
    return {d.id for d in result.datasets}


def test_anonymous_never_sees_restricted_dataset(db_session, locations):
    result = list_visible_datasets(db_session, ANONYMOUS, locations=locations)
    assert "restricted_station" not in _ids(result)
    assert result.total == 3


def test_authenticated_user_sees_restricted_dataset(db_session, locations):
    result = list_visible_datasets(db_session, LOGGED_IN, locations=locations)
    assert "restricted_station" in _ids(result)
    assert result.total == 4


def test_q_filters_by_title_substring_case_insensitive(db_session, locations):
    result = list_visible_datasets(db_session, ANONYMOUS, locations=locations, q="isfjord")
    assert _ids(result) == {"isfjord_radio_solar_park_measurements3"}


def test_q_matches_open_ended_metadata_values(db_session, locations):
    # all 3 real stations have a department containing "Arctic"
    result = list_visible_datasets(db_session, ANONYMOUS, locations=locations, q="ARCTIC")
    assert _ids(result) == {
        "isfjord_radio_solar_park_measurements3",
        "kapp_thordsen_10minute",
        "hanna_resvoll_10min",
    }


def test_platform_type_filter(db_session, locations):
    result = list_visible_datasets(db_session, ANONYMOUS, locations=locations, platform_type="mobile")
    assert _ids(result) == {"hanna_resvoll_10min"}


def test_standard_name_filter_requires_all_requested(db_session, locations):
    both = list_visible_datasets(
        db_session, ANONYMOUS, locations=locations, standard_names=["latitude", "longitude"]
    )
    assert _ids(both) == {"hanna_resvoll_10min"}

    # dew_point_temperature is mapped by the two fixed stations but not the boat
    shared = list_visible_datasets(
        db_session, ANONYMOUS, locations=locations, standard_names=["dew_point_temperature"]
    )
    assert _ids(shared) == {
        "isfjord_radio_solar_park_measurements3",
        "kapp_thordsen_10minute",
    }


def test_meta_filter_exact_department_narrows_to_one(db_session, locations):
    result = list_visible_datasets(
        db_session, ANONYMOUS, locations=locations, meta_filters=[("department", "Arctic Technology")]
    )
    assert _ids(result) == {"isfjord_radio_solar_park_measurements3"}


def test_meta_filter_substring_matches_multiple(db_session, locations):
    # Kapp Thordsen and Hanna Resvoll are both "Arctic Geophysics"; Isfjord is
    # "Arctic Technology" and must not match this narrower substring
    result = list_visible_datasets(
        db_session, ANONYMOUS, locations=locations, meta_filters=[("department", "Geophysics")]
    )
    assert _ids(result) == {"kapp_thordsen_10minute", "hanna_resvoll_10min"}


def test_results_sorted_by_id(db_session, locations):
    result = list_visible_datasets(db_session, LOGGED_IN, locations=locations)
    ids = [d.id for d in result.datasets]
    assert ids == sorted(ids)


def test_dataset_summary_shape_for_fixed_dataset(db_session, locations):
    result = list_visible_datasets(db_session, ANONYMOUS, locations=locations, q="kapp")
    summary = result.datasets[0]
    assert summary.title == "UNIS AGF Kapp Thordsen AWS"
    assert summary.platform_type == "fixed"
    assert "air_temperature" in summary.standard_names
    assert summary.metadata["department"] == "Arctic Geophysics"
    assert summary.position == {"lat": 78.4567, "lon": 15.3239, "elevation": 5}


def test_position_is_none_for_mobile_dataset(db_session, locations):
    result = list_visible_datasets(db_session, ANONYMOUS, locations=locations, q="resvoll")
    assert result.datasets[0].position is None
