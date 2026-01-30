"""Redis 客户端管理"""

from typing import Optional, Any
from app.core.settings import settings
import json


_redis_client = None


def get_redis_client():
    """
    获取 Redis 客户端

    Returns:
        Redis 客户端实例
    """
    global _redis_client

    if _redis_client is None:
        if settings.REDIS_URL:
            try:
                from redis import asyncio as aioredis
                _redis_client = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True
                )
                print(f"[REDIS] connected: {settings.REDIS_URL}")
            except Exception as e:
                print(f"[REDIS] init failed: {e}")
                _redis_client = None
        else:
            print("[REDIS] disabled (REDIS_URL not set)")
            _redis_client = None

    return _redis_client


async def redis_cache(key: str, value: Any, ttl: int = None) -> bool:
    """
    Redis 缓存操作

    Args:
        key: 缓存键
        value: 缓存值
        ttl: 过期时间（秒）

    Returns:
        bool: 是否成功
    """
    client = get_redis_client()
    if client is None:
        return False

    try:
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)

        if ttl:
            await client.setex(key, ttl, value)
        else:
            await client.set(key, value)

        return True
    except Exception as e:
        print(f"[REDIS] cache error: {e}")
        return False


async def redis_get(key: str) -> Optional[Any]:
    """
    从 Redis 获取缓存

    Args:
        key: 缓存键

    Returns:
        缓存值，如果不存在则返回 None
    """
    client = get_redis_client()
    if client is None:
        return None

    try:
        value = await client.get(key)
        if value:
            try:
                return json.loads(value)
            except:
                return value
        return None
    except Exception as e:
        print(f"[REDIS] get error: {e}")
        return None
