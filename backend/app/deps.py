"""依赖注入/初始化入口"""

from typing import AsyncGenerator
from fastapi import Depends
from app.core.settings import settings


async def get_redis():
    """
    获取 Redis 客户端依赖

    Yields:
        Redis 客户端
    """
    from infra.cache.redis_client import get_redis_client

    redis = get_redis_client()
    if redis is None:
        raise ValueError("Redis 未配置")

    try:
        yield redis
    finally:
        pass


async def get_db():
    """
    获取数据库连接依赖

    Yields:
        数据库连接
    """
    # TODO: 实现数据库连接依赖
    yield None


def get_settings():
    """
    获取配置依赖

    Returns:
        Settings: 配置对象
    """
    return settings
