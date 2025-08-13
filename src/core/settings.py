from __future__ import annotations

from functools import lru_cache
from typing import List, Union

from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # pydantic v2 配置：仅入口加载 .env，其余忽略多余环境变量
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")
    """
    集中化配置入口：统一从 .env / 环境变量读取。

    注意：当前阶段仅提供读取功能，逐步替换各模块对 os.getenv / load_dotenv 的直接使用。
    """

    # 基础与密钥
    DASHSCOPE_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    SENIVERSE_API_KEY: str = ""

    # RAG / 模型相关（默认值与现有代码保持一致）
    LLM_MODEL_NAME: str = "qwen-turbo-2025-07-15"
    EMBED_MODEL_NAME: str = "BAAI/bge-small-zh-v1.5"
    FORTUNE_LLM_MODEL: str = "qwen-turbo-2025-07-15"
    EVAL_EMBED_MODEL: str = "BAAI/bge-small-zh-v1.5"

    # 数据路径（可选覆盖）
    CSV_FILE_PATH: str = ""
    CSV_DIR_PATH: str = ""

    # Notion 集成
    ENABLE_NOTION: bool = False
    NOTION_API_KEY: str = ""
    NOTION_PAGE_IDS_RAW: str = Field(
        default="",
        validation_alias=AliasChoices("NOTION_PAGE_IDS", "notion_page_ids"),
        description="兼容逗号分隔或 JSON 数组的原始输入",
    )
    NOTION_DATABASE_ID: str = ""

    # 服务端口（供本地开发使用）
    PORT: int = 8000

    # 兼容：允许通过逗号分隔或 JSON 数组提供列表
    @staticmethod
    def _parse_csv_list(value: Union[str, List[str], None]) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        s = str(value).strip()
        # 兼容 JSON 数组和逗号分隔两种格式
        if s.startswith("[") and s.endswith("]"):
            try:
                import json

                arr = json.loads(s)
                if isinstance(arr, list):
                    return [str(x).strip() for x in arr if str(x).strip()]
            except Exception:
                pass
        return [x.strip() for x in s.split(",") if x.strip()]

    @property
    def NOTION_PAGE_IDS(self) -> List[str]:  # type: ignore[override]
        return self._parse_csv_list(self.NOTION_PAGE_IDS_RAW)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# 便捷别名
settings = get_settings()


