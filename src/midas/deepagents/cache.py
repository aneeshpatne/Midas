"""Fail-open Redis caching for expensive DeepAgent tool calls."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from redis import Redis
from redis.exceptions import RedisError

P = ParamSpec("P")
R = TypeVar("R")

DEFAULT_TOOL_CACHE_TTL_SECONDS = 24 * 60 * 60
_CACHE_VERSION = "v2"

cache_log = logging.getLogger(__name__)
_redis_client: Redis | None = None
_redis_url: str | None = None
_redis_unavailable = False
_MEMORY_CACHE_MAX_ENTRIES = 256
_memory_cache: OrderedDict[str, tuple[float, str, dict[str, str]]] = OrderedDict()
_memory_cache_lock = threading.Lock()


def _configured_redis_url() -> str | None:
    """Return the configured Redis URL; caching is disabled when it is absent."""
    return os.getenv("MIDAS_REDIS_URL") or os.getenv("REDIS_URL")


def _get_redis_client() -> Redis | None:
    """Create one process-local client, disabling Redis after a connection failure."""
    global _redis_client, _redis_url, _redis_unavailable

    url = _configured_redis_url()
    if not url:
        return None
    if url != _redis_url:
        _redis_client = None
        _redis_url = url
        _redis_unavailable = False
    if _redis_unavailable:
        return None
    if _redis_client is None:
        _redis_client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.5,
        )
    return _redis_client


def _jsonable(value: Any) -> Any:
    """Convert tool arguments into deterministic JSON-compatible values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted((_jsonable(item) for item in value), key=repr)
    return value


def _cache_key(tool_name: str, arguments: dict[str, Any]) -> str:
    serialized = json.dumps(
        _jsonable(arguments),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    return f"midas:tool-cache:{_CACHE_VERSION}:{tool_name}:{digest}"


def _bound_arguments(function: Callable[..., Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
    bound = inspect.signature(function).bind(*args, **kwargs)
    bound.apply_defaults()
    normalized: dict[str, Any] = {}
    for name, value in bound.arguments.items():
        if isinstance(value, str):
            value = " ".join(value.split())
            if name in {"symbol", "index"}:
                value = value.upper()
        elif isinstance(value, list):
            canonical_items = [_jsonable(item) for item in value]
            serialized_items = (
                json.dumps(item, sort_keys=True, default=str) for item in canonical_items
            )
            value = list(dict.fromkeys(serialized_items))
            value = [json.loads(item) for item in value]
        normalized[name] = value
    return normalized


def _is_cacheable_result(result: Any) -> bool:
    """Cache successful JSON tool responses, but never transient/error responses."""
    if not isinstance(result, str):
        return False
    try:
        payload = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("ok") is True


def _read(key: str) -> str | None:
    global _redis_unavailable
    with _memory_cache_lock:
        memory = _memory_cache.get(key)
        if memory is not None:
            expires_at, value, artifacts = memory
            if expires_at > time.monotonic():
                _memory_cache.move_to_end(key)
                from .artifacts import mark_cache_hit, materialize_cached_artifacts

                materialize_cached_artifacts(artifacts)
                return mark_cache_hit(value)
            _memory_cache.pop(key, None)

    client = _get_redis_client()
    if client is None:
        return None
    try:
        value = client.get(key)
        if not isinstance(value, str):
            return None
        artifact_value = client.get(f"{key}:artifacts")
        if isinstance(artifact_value, str):
            try:
                artifacts = json.loads(artifact_value)
                if isinstance(artifacts, dict):
                    from .artifacts import materialize_cached_artifacts

                    materialize_cached_artifacts(artifacts)
            except (OSError, TypeError, json.JSONDecodeError):
                cache_log.warning("Cached tool artifacts were invalid for %s", key)
        from .artifacts import mark_cache_hit

        return mark_cache_hit(value)
    except RedisError as exc:
        _redis_unavailable = True
        cache_log.warning("Redis tool cache unavailable; continuing without cache: %s", exc)
        return None


def _write(key: str, value: str, ttl_seconds: int) -> None:
    global _redis_unavailable
    from .artifacts import artifact_payload_for_cache

    artifacts = artifact_payload_for_cache(value)
    with _memory_cache_lock:
        _memory_cache[key] = (time.monotonic() + ttl_seconds, value, artifacts)
        _memory_cache.move_to_end(key)
        while len(_memory_cache) > _MEMORY_CACHE_MAX_ENTRIES:
            _memory_cache.popitem(last=False)

    client = _get_redis_client()
    if client is None:
        return
    try:
        client.set(key, value, ex=ttl_seconds)
        if artifacts:
            client.set(
                f"{key}:artifacts",
                json.dumps(artifacts, ensure_ascii=False, separators=(",", ":")),
                ex=ttl_seconds,
            )
    except RedisError as exc:
        _redis_unavailable = True
        cache_log.warning("Redis tool cache write failed; continuing without cache: %s", exc)


def redis_cached_tool(
    tool_name: str,
    *,
    ttl_seconds: int = DEFAULT_TOOL_CACHE_TTL_SECONDS,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Cache a successful tool response by its fully-bound arguments."""
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds must be >= 1")

    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                key = _cache_key(tool_name, _bound_arguments(function, *args, **kwargs))
                cached = _read(key)
                if cached is not None:
                    cache_log.info("Redis tool cache hit for %s", tool_name)
                    return cached
                result = await function(*args, **kwargs)
                if _is_cacheable_result(result):
                    _write(key, result, ttl_seconds)
                return result

            return async_wrapper

        @wraps(function)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            key = _cache_key(tool_name, _bound_arguments(function, *args, **kwargs))
            cached = _read(key)
            if cached is not None:
                cache_log.info("Redis tool cache hit for %s", tool_name)
                return cached
            result = function(*args, **kwargs)
            if _is_cacheable_result(result):
                _write(key, result, ttl_seconds)
            return result

        return sync_wrapper

    return decorator
