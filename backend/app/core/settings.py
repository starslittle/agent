from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    # 所有启动方式统一读取仓库根目录 .env；系统环境变量优先级更高。
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    """
    集中化配置入口：统一从仓库根目录 .env / 系统环境变量读取。
    """

    # 基础与密钥
    DASHSCOPE_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    SENIVERSE_API_KEY: str = ""
    INTERNAL_AGENT_SECRET: str = ""

    # RAG / 模型相关（默认值与现有代码保持一致）
    LLM_MODEL_NAME: str = "deepseek-v3.2"
    EMBED_MODEL_NAME: str = "BAAI/bge-small-zh-v1.5"
    FORTUNE_LLM_MODEL: str = "deepseek-v3.2"
    EVAL_EMBED_MODEL: str = "BAAI/bge-small-zh-v1.5"

    # 数据路径（可选覆盖）
    CSV_FILE_PATH: str = ""
    CSV_DIR_PATH: str = ""

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
    
    # 流式分片配置（字符数）。数值越小，chunk 次数越多；0 表示不拆分
    STREAM_CHUNK_SIZE: int = 24

    # Redis 配置
    REDIS_URL: str = ""
    REDIS_TTL: int = 120  # /query 结果缓存默认 120 秒，0 表示禁用
    
    # Agent执行限制（默认值，可被 .env 覆盖）
    DEFAULT_MAX_ITERATIONS: int = 30
    DEFAULT_MAX_EXECUTION_TIME: int = 300

    # 在所有设置加载完成后解析 DATABASE_URL
    def model_post_init(self, __context: Any) -> None:
        self._build_database_url()
        self._ensure_db_encoding()
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

    def _ensure_db_encoding(self) -> None:
        """确保 PostgreSQL 连接字符串包含正确的编码参数"""
        if self.DATABASE_URL and self.DATABASE_URL.startswith("postgresql"):
            # 移除任何现有的错误编码参数
            import re
            # 移除可能存在的错误格式
            self.DATABASE_URL = re.sub(r'\?options=-c[^&]*', '', self.DATABASE_URL)
            self.DATABASE_URL = re.sub(r'&options=-c[^&]*', '', self.DATABASE_URL)
            
            # 如果没有 client_encoding 参数，则添加正确的参数
            if "client_encoding" not in self.DATABASE_URL:
                separator = "?" if "?" not in self.DATABASE_URL else "&"
                self.DATABASE_URL += f"{separator}client_encoding=utf8"

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
