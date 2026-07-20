from __future__ import annotations

import threading
from typing import Any

import httpx
from cachetools import TTLCache

_LOGIN_PATH = "/api/auth/login"
_DEVICES_PATH = "/api/tenant/devices"


class ThingsBoardAuthError(RuntimeError):
    """Login to the ThingsBoard REST API failed (bad credentials / unreachable)."""


class ThingsBoardClient:
    """Thin synchronous wrapper around the ThingsBoard REST API, shared by
    ThingsBoardConfigProvider and ThingsBoardDataProvider (providers/config/
    thingsboard.py, providers/data/thingsboard/provider.py) as one
    process-lifetime singleton (see sources.py) so login happens once, not on
    every request.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        timeout: float = 30.0,
        discovery_ttl_seconds: float = 3600,
    ):
        self._username = username
        self._password = password
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self._token: str | None = None
        self._login_lock = threading.Lock()
        self._discovery_cache: TTLCache = TTLCache(maxsize=1, ttl=discovery_ttl_seconds)

    def close(self) -> None:
        self._http.close()

    def _login(self) -> None:
        response = self._http.post(
            _LOGIN_PATH, json={"username": self._username, "password": self._password}
        )
        if response.status_code != 200:
            raise ThingsBoardAuthError(f"ThingsBoard login failed: HTTP {response.status_code}")
        self._token = response.json()["token"]

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
        with self._login_lock:
            if self._token is None:
                self._login()
        response = self._http.request(method, path, params=params, headers=self._auth_headers())

        if response.status_code == 401:
            with self._login_lock:
                self._login()
            response = self._http.request(method, path, params=params, headers=self._auth_headers())

        return response

    def _auth_headers(self) -> dict[str, str]:
        return {"X-Authorization": f"Bearer {self._token}"}

    def list_devices(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        page = 0
        while True:
            response = self._request(
                "GET", _DEVICES_PATH, params={"pageSize": page_size, "page": page}
            )
            response.raise_for_status()
            payload = response.json()
            devices.extend(payload.get("data", []))
            if not payload.get("hasNext"):
                break
            page += 1
        return devices

    def get_device_by_name(self, device_name: str) -> dict[str, Any] | None:
        response = self._request("GET", _DEVICES_PATH, params={"deviceName": device_name})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def get_server_attribute(self, device_id: str, key: str) -> Any | None:
        response = self._request(
            "GET",
            f"/api/plugins/telemetry/DEVICE/{device_id}/values/attributes/SERVER_SCOPE",
            params={"keys": key},
        )
        response.raise_for_status()
        entries = response.json()
        if not entries:
            return None
        return entries[0]["value"]

    def get_latest_telemetry(self, device_id: str) -> dict[str, tuple[int, Any]]:
        response = self._request(
            "GET",
            f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
            params={"useStrictDataTypes": "true"},
        )
        response.raise_for_status()
        payload = response.json()
        return {key: (points[0]["ts"], points[0]["value"]) for key, points in payload.items() if points}

    def get_timeseries(
        self,
        device_id: str,
        keys: list[str],
        start_ms: int,
        end_ms: int,
        *,
        limit: int = 100_000,
    ) -> dict[str, list[tuple[int, Any]]]:
        response = self._request(
            "GET",
            f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
            params={
                "keys": ",".join(keys),
                "startTs": start_ms,
                "endTs": end_ms,
                "limit": limit,
                "orderBy": "ASC",
                "useStrictDataTypes": "true",
            },
        )
        response.raise_for_status()
        payload = response.json()
        return {key: [(p["ts"], p["value"]) for p in points] for key, points in payload.items()}

    def list_device_names_with_attribute(self, key: str) -> list[str]:
        """Every tenant device name that has a non-empty SERVER_SCOPE `key`
        attribute, throttled by an in-process TTL cache (constructor's
        `discovery_ttl_seconds`) rather than re-probing every device on every
        call — this is the expensive, N+1-HTTP-call discovery fan-out
        (implementation_plan.md-style tradeoff, confirmed acceptable at a
        modest tenant device count).
        """
        cached = self._discovery_cache.get("names")
        if cached is not None:
            return cached

        names = sorted(
            device["name"]
            for device in self.list_devices()
            if self.get_server_attribute(device["id"]["id"], key) is not None
        )
        self._discovery_cache["names"] = names
        return names
