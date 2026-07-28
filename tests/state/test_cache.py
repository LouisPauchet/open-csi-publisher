from __future__ import annotations

import redis

from open_csi_publisher import settings as settings_module
from open_csi_publisher.state import cache as cache_module
from open_csi_publisher.state.cache import NullParseCache, ParseCache, get_parse_cache


class FakeRedisClient:
    """A minimal in-memory stand-in for redis.Redis, satisfying just the two
    methods ParseCache actually calls. TTL enforcement is redis's own job, not
    ParseCache's, so this fake doesn't simulate expiry — tests instead assert
    the ttl value ParseCache passes through to setex."""

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.setex_calls: list[tuple[str, int, bytes]] = []

    def get(self, key: str):
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: bytes):
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value


class FailingRedisClient:
    def get(self, key: str):
        raise redis.exceptions.RedisError("connection refused")

    def setex(self, key: str, ttl: int, value: bytes):
        raise redis.exceptions.RedisError("connection refused")


def test_parse_cache_get_returns_none_on_miss():
    cache = ParseCache(FakeRedisClient())
    assert cache.get("missing") is None


def test_parse_cache_set_then_get_round_trips_bytes():
    cache = ParseCache(FakeRedisClient())
    cache.set("key-1", b"parsed-bytes", ttl=60)
    assert cache.get("key-1") == b"parsed-bytes"


def test_parse_cache_set_passes_ttl_through_to_client():
    client = FakeRedisClient()
    cache = ParseCache(client)
    cache.set("key-1", b"parsed-bytes", ttl=123)
    assert client.setex_calls == [("key-1", 123, b"parsed-bytes")]


def test_parse_cache_get_swallows_redis_error_and_treats_as_miss(caplog):
    cache = ParseCache(FailingRedisClient())
    assert cache.get("key-1") is None
    assert "redis" in caplog.text.lower()


def test_parse_cache_set_swallows_redis_error(caplog):
    cache = ParseCache(FailingRedisClient())
    cache.set("key-1", b"parsed-bytes", ttl=60)  # must not raise
    assert "redis" in caplog.text.lower()


def test_null_parse_cache_get_always_misses():
    cache = NullParseCache()
    assert cache.get("anything") is None


def test_null_parse_cache_set_is_a_noop():
    cache = NullParseCache()
    cache.set("anything", b"value", ttl=60)  # must not raise
    assert cache.get("anything") is None


def test_get_parse_cache_returns_null_cache_when_redis_url_unset(monkeypatch):
    monkeypatch.setattr(settings_module.settings, "redis_url", None)
    cache_module.get_parse_cache.cache_clear()

    assert isinstance(get_parse_cache(), NullParseCache)


def test_get_parse_cache_returns_parse_cache_when_redis_url_set(monkeypatch):
    monkeypatch.setattr(settings_module.settings, "redis_url", "redis://localhost:6379/0")
    cache_module.get_parse_cache.cache_clear()

    assert isinstance(get_parse_cache(), ParseCache)


def test_get_parse_cache_is_a_process_lifetime_singleton(monkeypatch):
    monkeypatch.setattr(settings_module.settings, "redis_url", "redis://localhost:6379/0")
    cache_module.get_parse_cache.cache_clear()

    assert get_parse_cache() is get_parse_cache()
