from langchain_core.tools import tool
import datetime

@tool
def get_current_date() -> str:
    """返回今天的日期，格式：YYYY年MM月DD日。"""
    return datetime.date.today().strftime("%Y年%m月%d日")
