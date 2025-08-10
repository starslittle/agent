import os
import requests
from langchain_core.tools import tool

@tool
def get_seniverse_weather(location: str) -> str:
    """
    查询中国城市当前天气。参数示例："杭州"、"北京"。
    需要在 .env 设置 SENIVERSE_API_KEY。
    """
    api_key = os.getenv("SENIVERSE_API_KEY", "")
    if not api_key:
        return "错误：未配置 SENIVERSE_API_KEY。"
    url = "https://api.seniverse.com/v3/weather/now.json"
    params = {
        "key": api_key,
        "location": location,
        "language": "zh-Hans",
        "unit": "c",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()["results"][0]
        city = data["location"]["name"]
        text = data["now"]["text"]
        temp = data["now"]["temperature"]
        return f"{city}当前天气：{text}，{temp}°C。"
    except Exception as e:
        return f"天气查询失败：{e}"
