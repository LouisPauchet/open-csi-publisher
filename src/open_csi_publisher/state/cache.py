from __future__ import annotations

from functools import lru_cache
from typing import Protocol

import redis
from loguru import logger

from open_csi_publisher.settings import settings


class _RedisLike(Protocol):
    def get(self, key: str) -> bytes | None: ...
    def setex(self, key: str, ttl: int, value: bytes) -> object: ...


class NullParseCache:
    """Used when settings.redis_url is unset — always misses, set() is a
    no-op. Callers never need an `if redis configured` branch.

    `enabled = False` lets a caller distinguish "no real cache is backing
    this" from "a cache is configured but this particular key missed" —
    providers use it to skip the always-full-parse-then-subset path (worth it
    only when a real cache can actually save a future call) and fall back to
    today's cheaper partial/usecols read when there's no cache to benefit
    from at all.
    """

    enabled = False

    def get(self, key: str) -> bytes | None:
        return None

    def set(self, key: str, value: bytes, ttl: int) -> None:
        pass


class ParseCache:
    """Thin wrapper around a redis-client-like object, used to cache parsed
    LoggerNet/generic-CSV file content (providers/data/loggernet/provider.py,
    providers/data/generic_csv/provider.py). Every call is wrapped so a
    down/unreachable Redis degrades to always-miss rather than raising into
    request handling — the same graceful-degrade convention as
    Settings.oidc_configured.
    """

    enabled = True

    def __init__(self, client: _RedisLike):
        self._client = client

    def get(self, key: str) -> bytes | None:
        try:
            return self._client.get(key)
        except redis.exceptions.RedisError:
            logger.warning("redis cache read failed for key {!r}, treating as a miss", key)
            return None

    def set(self, key: str, value: bytes, ttl: int) -> None:
        try:
            self._client.setex(key, ttl, value)
        except redis.exceptions.RedisError:
            logger.warning("redis cache write failed for key {!r}, skipping", key)


@lru_cache(maxsize=None)
def get_parse_cache() -> ParseCache | NullParseCache:
    """Process-lifetime singleton (mirrors sources.py's _get_thingsboard_client
    pattern). Built once from settings.redis_url — a NullParseCache when unset."""
    if not settings.redis_url:
        return NullParseCache()
    return ParseCache(redis.Redis.from_url(settings.redis_url))
