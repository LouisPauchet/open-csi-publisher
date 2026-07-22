from __future__ import annotations

import httpx
import pytest
import respx

from open_csi_publisher.providers.thingsboard_client import (
    ThingsBoardAuthError,
    ThingsBoardClient,
)

BASE_URL = "http://tb.example.test"


def _login_route(token: str = "token-1"):
    return respx.post(f"{BASE_URL}/api/auth/login").mock(
        return_value=httpx.Response(200, json={"token": token, "refreshToken": "refresh-1"})
    )


@pytest.fixture
def client():
    c = ThingsBoardClient(BASE_URL, "admin", "secret")
    yield c
    c.close()


@respx.mock
def test_login_happens_lazily_and_token_sent_as_bearer(client):
    login = _login_route()
    devices_route = respx.get(f"{BASE_URL}/api/tenant/devices").mock(
        return_value=httpx.Response(200, json={"data": [], "hasNext": False})
    )

    assert login.call_count == 0
    client.list_devices()

    assert login.call_count == 1
    sent_request = devices_route.calls[0].request
    assert sent_request.headers["X-Authorization"] == "Bearer token-1"


@respx.mock
def test_login_failure_raises_auth_error():
    respx.post(f"{BASE_URL}/api/auth/login").mock(return_value=httpx.Response(401, json={}))
    c = ThingsBoardClient(BASE_URL, "admin", "wrong")
    with pytest.raises(ThingsBoardAuthError):
        c.list_devices()


def test_constructing_without_credentials_or_api_key_raises():
    with pytest.raises(ValueError):
        ThingsBoardClient(BASE_URL)


@respx.mock
def test_api_key_sent_without_login():
    login = respx.post(f"{BASE_URL}/api/auth/login").mock(
        return_value=httpx.Response(200, json={"token": "token-1", "refreshToken": "refresh-1"})
    )
    devices_route = respx.get(f"{BASE_URL}/api/tenant/devices").mock(
        return_value=httpx.Response(200, json={"data": [], "hasNext": False})
    )

    c = ThingsBoardClient(BASE_URL, api_key="tb_secret")
    try:
        c.list_devices()
    finally:
        c.close()

    assert login.call_count == 0
    sent_request = devices_route.calls[0].request
    assert sent_request.headers["X-Authorization"] == "ApiKey tb_secret"


@respx.mock
def test_401_triggers_one_relogin_and_retry(client):
    login = respx.post(f"{BASE_URL}/api/auth/login").mock(
        side_effect=[
            httpx.Response(200, json={"token": "token-1", "refreshToken": "r1"}),
            httpx.Response(200, json={"token": "token-2", "refreshToken": "r2"}),
        ]
    )
    devices_route = respx.get(f"{BASE_URL}/api/tenant/devices").mock(
        side_effect=[
            httpx.Response(401, json={}),
            httpx.Response(200, json={"data": [], "hasNext": False}),
        ]
    )

    client.list_devices()

    assert login.call_count == 2
    assert devices_route.call_count == 2
    assert devices_route.calls[1].request.headers["X-Authorization"] == "Bearer token-2"


@respx.mock
def test_list_devices_paginates_across_pages(client):
    _login_route()
    respx.get(f"{BASE_URL}/api/tenant/devices", params={"pageSize": "100", "page": "0"}).mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"name": "station_a"}], "hasNext": True},
        )
    )
    respx.get(f"{BASE_URL}/api/tenant/devices", params={"pageSize": "100", "page": "1"}).mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"name": "station_b"}], "hasNext": False},
        )
    )

    devices = client.list_devices()

    assert [d["name"] for d in devices] == ["station_a", "station_b"]


@respx.mock
def test_get_device_by_name_returns_none_on_404(client):
    _login_route()
    respx.get(f"{BASE_URL}/api/tenant/devices", params={"deviceName": "missing"}).mock(
        return_value=httpx.Response(404, json={})
    )

    assert client.get_device_by_name("missing") is None


@respx.mock
def test_get_device_by_name_returns_device_on_200(client):
    _login_route()
    device = {"id": {"id": "dev-1", "entityType": "DEVICE"}, "name": "station_a", "createdTime": 123}
    respx.get(f"{BASE_URL}/api/tenant/devices", params={"deviceName": "station_a"}).mock(
        return_value=httpx.Response(200, json=device)
    )

    assert client.get_device_by_name("station_a") == device


@respx.mock
def test_get_server_attribute_returns_none_when_empty(client):
    _login_route()
    respx.get(
        f"{BASE_URL}/api/plugins/telemetry/DEVICE/dev-1/values/attributes/SERVER_SCOPE"
    ).mock(return_value=httpx.Response(200, json=[]))

    assert client.get_server_attribute("dev-1", "open-csi-publisher-config") is None


@respx.mock
def test_get_server_attribute_returns_value(client):
    _login_route()
    respx.get(
        f"{BASE_URL}/api/plugins/telemetry/DEVICE/dev-1/values/attributes/SERVER_SCOPE"
    ).mock(
        return_value=httpx.Response(
            200,
            json=[{"key": "open-csi-publisher-config", "value": '{"id": "x"}', "lastUpdateTs": 1}],
        )
    )

    assert client.get_server_attribute("dev-1", "open-csi-publisher-config") == '{"id": "x"}'


@respx.mock
def test_get_latest_telemetry_reshapes_and_sets_strict_types_param(client):
    _login_route()
    route = respx.get(f"{BASE_URL}/api/plugins/telemetry/DEVICE/dev-1/values/timeseries").mock(
        return_value=httpx.Response(
            200,
            json={
                "temp": [{"ts": 1000, "value": 5.5}],
                "status": [{"ts": 1000, "value": "ok"}],
            },
        )
    )

    result = client.get_latest_telemetry("dev-1")

    assert result == {"temp": (1000, 5.5), "status": (1000, "ok")}
    sent_params = route.calls[0].request.url.params
    assert sent_params["useStrictDataTypes"] == "true"
    assert "keys" not in sent_params
    assert "startTs" not in sent_params


@respx.mock
def test_get_timeseries_reshapes_and_sends_expected_params(client):
    _login_route()
    route = respx.get(f"{BASE_URL}/api/plugins/telemetry/DEVICE/dev-1/values/timeseries").mock(
        return_value=httpx.Response(
            200,
            json={
                "temp": [{"ts": 1000, "value": 5.5}, {"ts": 2000, "value": 6.0}],
            },
        )
    )

    result = client.get_timeseries("dev-1", ["temp"], start_ms=1000, end_ms=2000)

    assert result == {"temp": [(1000, 5.5), (2000, 6.0)]}
    sent_params = route.calls[0].request.url.params
    assert sent_params["keys"] == "temp"
    assert sent_params["startTs"] == "1000"
    assert sent_params["endTs"] == "2000"
    assert sent_params["orderBy"] == "ASC"
    assert sent_params["useStrictDataTypes"] == "true"


@respx.mock
def test_list_device_names_with_attribute_filters_and_sorts():
    _login_route()
    respx.get(f"{BASE_URL}/api/tenant/devices").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": {"id": "dev-b"}, "name": "station_b"},
                    {"id": {"id": "dev-a"}, "name": "station_a"},
                ],
                "hasNext": False,
            },
        )
    )
    respx.get(
        f"{BASE_URL}/api/plugins/telemetry/DEVICE/dev-b/values/attributes/SERVER_SCOPE"
    ).mock(return_value=httpx.Response(200, json=[{"key": "k", "value": "{}"}]))
    respx.get(
        f"{BASE_URL}/api/plugins/telemetry/DEVICE/dev-a/values/attributes/SERVER_SCOPE"
    ).mock(return_value=httpx.Response(200, json=[]))

    c = ThingsBoardClient(BASE_URL, "admin", "secret", discovery_ttl_seconds=3600)
    try:
        assert c.list_device_names_with_attribute("k") == ["station_b"]
    finally:
        c.close()


@respx.mock
def test_list_device_names_with_attribute_caches_within_ttl():
    _login_route()
    devices_route = respx.get(f"{BASE_URL}/api/tenant/devices").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": {"id": "dev-a"}, "name": "station_a"}], "hasNext": False}
        )
    )
    respx.get(
        f"{BASE_URL}/api/plugins/telemetry/DEVICE/dev-a/values/attributes/SERVER_SCOPE"
    ).mock(return_value=httpx.Response(200, json=[{"key": "k", "value": "{}"}]))

    c = ThingsBoardClient(BASE_URL, "admin", "secret", discovery_ttl_seconds=3600)
    try:
        first = c.list_device_names_with_attribute("k")
        second = c.list_device_names_with_attribute("k")
        assert first == second == ["station_a"]
        assert devices_route.call_count == 1
    finally:
        c.close()


@respx.mock
def test_list_device_names_with_attribute_reprobes_after_ttl_expires():
    _login_route()
    devices_route = respx.get(f"{BASE_URL}/api/tenant/devices").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": {"id": "dev-a"}, "name": "station_a"}], "hasNext": False}
        )
    )
    respx.get(
        f"{BASE_URL}/api/plugins/telemetry/DEVICE/dev-a/values/attributes/SERVER_SCOPE"
    ).mock(return_value=httpx.Response(200, json=[{"key": "k", "value": "{}"}]))

    c = ThingsBoardClient(BASE_URL, "admin", "secret", discovery_ttl_seconds=0.01)
    try:
        c.list_device_names_with_attribute("k")
        import time

        time.sleep(0.05)
        c.list_device_names_with_attribute("k")
        assert devices_route.call_count == 2
    finally:
        c.close()
