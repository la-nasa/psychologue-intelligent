from __future__ import annotations

import time

import redis.asyncio as redis

from app.core.config import get_settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    settings = get_settings()
    if settings.env == "testing":
        # pytest-asyncio : une boucle par test ; un pool Redis mis en cache
        # lierait ses connexions à la première boucle. On recrée à chaque appel.
        return redis.from_url(settings.redis_url, decode_responses=True)
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# Rate limiter distribué à fenêtre glissante (remplace le limiteur en mémoire
# de la v1 — threat-model-v2 TH-10). Partagé entre toutes les instances de l'API.
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  return 0
end
redis.call('ZADD', key, now, now .. '-' .. math.random())
redis.call('PEXPIRE', key, window)
return 1
"""


async def rate_limit_allow(bucket: str, key: str, *, limit: int, window_seconds: int) -> bool:
    client = get_redis()
    now_ms = int(time.time() * 1000)
    # Les args ARGV d'un script Redis sont transmis en chaînes ; `tonumber()` côté Lua.
    result = await client.eval(
        _SLIDING_WINDOW_LUA,
        1,
        f"rl:{bucket}:{key}",
        str(now_ms),
        str(window_seconds * 1000),
        str(limit),
    )
    return bool(result)
