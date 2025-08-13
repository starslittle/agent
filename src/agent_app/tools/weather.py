import requests
from langchain_core.tools import tool
from src.core.settings import settings

@tool
def get_seniverse_weather(location: str) -> str:
    """
    查询中国城市当前天气。参数示例："杭州"、"北京"。
    需要在 .env 设置 SENIVERSE_API_KEY。
    """
    api_key = settings.SENIVERSE_API_KEY or ""
    if not api_key:
        return "错误：未配置 SENIVERSE_API_KEY。"
    # 现在接口：当前天气 + 未来三日预报，便于拿最高/最低温
    now_url = "https://api.seniverse.com/v3/weather/now.json"
    daily_url = "https://api.seniverse.com/v3/weather/daily.json"
    common = {"key": api_key, "location": location, "language": "zh-Hans", "unit": "c"}
    try:
        r_now = requests.get(now_url, params=common, timeout=15)
        r_now.raise_for_status()
        data_now = r_now.json()["results"][0]

        r_daily = requests.get({**{"url": daily_url}}.get("url"), params={**common, "start": 0, "days": 1}, timeout=15)
        r_daily.raise_for_status()
        data_daily = r_daily.json()["results"][0]
        city = data_now["location"]["name"]
        text = data_now["now"]["text"]
        temp = data_now["now"]["temperature"]
        daily0 = (data_daily.get("daily") or [{}])[0]
        high = daily0.get("high")
        low = daily0.get("low")
        extra = f" 最高{high}°C，最低{low}°C。" if high and low else ""
        return f"{city}当前天气：{text}，当前温度：{temp}°C。" + extra
    except Exception as e:
        return f"天气查询失败：{e}"
