from __future__ import annotations

import json
import time
from typing import Any, Optional

import redis.asyncio as redis

from app.core.config import get_settings

_redis: Optional[redis.Redis] = None
_use_memory = False
_memory_store: dict[str, tuple[str, float]] = {}


async def get_redis() -> redis.Redis:
    global _redis, _use_memory
    if _redis is not None:
        return _redis
    settings = get_settings()
    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        _redis = client
        return client
    except Exception:
        _use_memory = True
        return redis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)


class LockService:
    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client
        settings = get_settings()
        self.ttl = settings.LOCK_TTL_SECONDS

    def _key(self, image_id: str) -> str:
        return f"lock:image:{image_id}"

    async def _mem_get(self, key: str) -> Optional[str]:
        item = _memory_store.get(key)
        if not item:
            return None
        value, expires = item
        if expires < time.time():
            _memory_store.pop(key, None)
            return None
        return value

    async def _mem_set(self, key: str, value: str) -> None:
        _memory_store[key] = (value, time.time() + self.ttl)

    async def acquire(self, image_id: str, user_id: str, display_name: str) -> tuple:
        key = self._key(image_id)
        if _use_memory:
            existing_raw = await self._mem_get(key)
        else:
            existing_raw = await self.redis.get(key)
        if existing_raw:
            data = json.loads(existing_raw)
            if data["user_id"] != user_id:
                return False, data
        payload = {"user_id": user_id, "display_name": display_name}
        encoded = json.dumps(payload)
        if _use_memory:
            await self._mem_set(key, encoded)
        else:
            await self.redis.set(key, encoded, ex=self.ttl)
        return True, payload

    async def renew(self, image_id: str, user_id: str) -> bool:
        key = self._key(image_id)
        if _use_memory:
            existing_raw = await self._mem_get(key)
        else:
            existing_raw = await self.redis.get(key)
        if not existing_raw:
            return False
        data = json.loads(existing_raw)
        if data["user_id"] != user_id:
            return False
        if _use_memory:
            await self._mem_set(key, existing_raw)
        else:
            await self.redis.expire(key, self.ttl)
        return True

    async def release(self, image_id: str, user_id: str) -> bool:
        key = self._key(image_id)
        if _use_memory:
            existing_raw = await self._mem_get(key)
        else:
            existing_raw = await self.redis.get(key)
        if not existing_raw:
            return False
        data = json.loads(existing_raw)
        if data["user_id"] != user_id:
            return False
        if _use_memory:
            _memory_store.pop(key, None)
        else:
            await self.redis.delete(key)
        return True

    async def get(self, image_id: str) -> Optional[dict]:
        if _use_memory:
            existing_raw = await self._mem_get(self._key(image_id))
        else:
            existing_raw = await self.redis.get(self._key(image_id))
        return json.loads(existing_raw) if existing_raw else None


class PubSubService:
    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client

    def channel(self, project_id: str) -> str:
        return f"ws:project:{project_id}"

    def image_channel(self, image_id: str) -> str:
        return f"ws:image:{image_id}"

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        if _use_memory:
            return
        await self.redis.publish(channel, json.dumps(message))
