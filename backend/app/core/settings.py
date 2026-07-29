from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    # 独立 Agent Service 仅从 backend/.env（若存在）和系统环境变量读取。
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    """
    集中化配置入口：统一从 backend/.env / 系统环境变量读取。
    """

    # 基础与密钥
    DASHSCOPE_API_KEY: str = ""
    MODEL_PROVIDER: str = "dashscope_openai"
    MODEL_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MODEL_REQUEST_TIMEOUT_SECONDS: float = 120.0
    TAVILY_API_KEY: str = ""
    INTERNAL_AGENT_SECRET: str = ""
    AGENT_SERVICE_VERSION: str = "dev"
    AGENT_PROTOCOL_VERSION: int = 1
    AGENT_RUNTIME_RETENTION_SECONDS: int = 1800
    AGENT_RUNTIME_STORE: Literal["memory", "postgres"] = "memory"
    AGENT_RUNTIME_DATABASE_URL: str = ""
    AGENT_RUNTIME_LEASE_SECONDS: int = 30
    AGENT_RUNTIME_EVENT_POLL_SECONDS: float = 0.25
    AGENT_RUNTIME_CHECKPOINT_SETUP: bool = False
    AGENT_RUNTIME_COORDINATION: Literal["none", "redis"] = "none"
    AGENT_RUNTIME_REDIS_CHANNEL_PREFIX: str = "qidian:agent-runtime"
    AGENT_RUNTIME_MAINTENANCE_SECONDS: int = 300
    AGENT_MAX_REQUEST_BYTES: int = 1048576
    # Retained for deployment compatibility; only the single LangGraph v1
    # implementation exists after the migration.
    AGENT_EXECUTION_ENGINE: Literal["langgraph_v1"] = "langgraph_v1"
    APP_TIMEZONE: str = "Asia/Shanghai"

    # 模型
    LLM_MODEL_NAME: str = "deepseek-v4-flash"

    # 服务端口（供本地开发使用）
    PORT: int = 8000
    
    # 数据库配置
    DATABASE_URL: str = ""
    POSTGRES_DB: str = "agent_db"
    POSTGRES_USER: str = "qidian_agent"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    ENVIRONMENT: str = "development"
    
    # Redis Runtime 通知
    REDIS_URL: str = ""

    # 在所有设置加载完成后解析 DATABASE_URL
    def model_post_init(self, __context: Any) -> None:
        self._build_database_url()
        self.DATABASE_URL = self._normalize_database_url(self.DATABASE_URL)
        if not self.AGENT_RUNTIME_DATABASE_URL:
            self.AGENT_RUNTIME_DATABASE_URL = self.DATABASE_URL
        else:
            self.AGENT_RUNTIME_DATABASE_URL = self._normalize_database_url(
                self.AGENT_RUNTIME_DATABASE_URL
            )
        self._parse_database_url()

    def _build_database_url(self) -> None:
        """未显式配置 DATABASE_URL 时，由唯一的 POSTGRES_* 配置组合生成。"""
        if self.DATABASE_URL or not self.POSTGRES_PASSWORD:
            return
        user = quote_plus(self.POSTGRES_USER)
        password = quote_plus(self.POSTGRES_PASSWORD)
        database = quote_plus(self.POSTGRES_DB)
        self.DATABASE_URL = (
            f"postgresql://{user}:{password}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{database}"
        )

    @staticmethod
    def _normalize_database_url(value: str) -> str:
        """Normalize PostgreSQL client encoding without exposing credentials."""
        import re

        if not value or not value.startswith("postgresql"):
            return value
        normalized = re.sub(r"\?options=-c[^&]*", "", value)
        normalized = re.sub(r"&options=-c[^&]*", "", normalized)
        if "client_encoding" not in normalized:
            separator = "?" if "?" not in normalized else "&"
            normalized += f"{separator}client_encoding=utf8"
        return normalized

    def _parse_database_url(self) -> None:
        import re
        if self.DATABASE_URL:
            match = re.match(r"postgresql://(.*?):(.*?)@", self.DATABASE_URL)
            if match:
                self.POSTGRES_USER = match.group(1)
                self.POSTGRES_PASSWORD = match.group(2)

@lru_cache()
def get_settings() -> Settings:
    return Settings()


# 便捷别名
settings = get_settings()
