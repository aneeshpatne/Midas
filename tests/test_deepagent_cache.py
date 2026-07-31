import asyncio
import json

import pytest

from midas.deepagents import cache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.ttls[key] = ex


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    client = FakeRedis()
    cache._memory_cache.clear()
    monkeypatch.setattr(cache, "_get_redis_client", lambda: client)
    return client


@pytest.mark.asyncio
async def test_async_tool_cache_reuses_success_and_applies_defaults(fake_redis: FakeRedis) -> None:
    calls = 0

    @cache.redis_cached_tool("example")
    async def lookup(query: str, limit: int = 5) -> str:
        nonlocal calls
        calls += 1
        return json.dumps({"ok": True, "query": query, "limit": limit})

    first = await lookup("TCS")
    second = await lookup(query="TCS", limit=5)

    assert first == second
    assert calls == 1
    assert list(fake_redis.ttls.values()) == [cache.DEFAULT_TOOL_CACHE_TTL_SECONDS]


def test_tool_cache_does_not_store_errors(fake_redis: FakeRedis) -> None:
    calls = 0

    @cache.redis_cached_tool("example")
    def lookup(query: str) -> str:
        nonlocal calls
        calls += 1
        return json.dumps({"ok": False, "query": query, "error": "temporary"})

    lookup("TCS")
    lookup("TCS")

    assert calls == 2
    assert fake_redis.values == {}


@pytest.mark.asyncio
async def test_tool_cache_keeps_distinct_arguments_separate(fake_redis: FakeRedis) -> None:
    calls: list[str] = []

    @cache.redis_cached_tool("example")
    async def lookup(query: str) -> str:
        calls.append(query)
        await asyncio.sleep(0)
        return json.dumps({"ok": True, "query": query})

    await lookup("TCS")
    await lookup("INFY")
    await lookup("TCS")

    assert calls == ["TCS", "INFY"]
    assert len(fake_redis.values) == 2
