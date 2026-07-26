from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from app.core.settings import settings

@tool
def get_current_date() -> str:
    """返回今天的日期，格式：YYYY年MM月DD日。"""
    try:
        timezone = ZoneInfo(settings.APP_TIMEZONE)
    except Exception:
        timezone = ZoneInfo("UTC")
    return datetime.now(timezone).strftime("%Y年%m月%d日")
