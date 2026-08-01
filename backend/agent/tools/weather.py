from __future__ import annotations

from typing import Any


_WEATHER_LABELS = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    56: "轻微冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻微冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "小阵雨",
    81: "中阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴强冰雹",
}


def _first(values: Any) -> Any:
    if isinstance(values, list) and values:
        return values[0]
    return None


def _display_location(item: dict[str, Any]) -> str:
    parts = [item.get("name"), item.get("admin1"), item.get("country")]
    return "，".join(str(value) for value in parts if value)


def get_weather(location: str) -> str:
    """Fetch deterministic current conditions and today's forecast."""

    import requests

    normalized = location.strip()
    geocoding = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": normalized,
            "count": 1,
            "language": "zh",
            "format": "json",
        },
        timeout=12,
    )
    geocoding.raise_for_status()
    locations = geocoding.json().get("results") or []
    if not locations:
        raise LookupError("weather_location_not_found")

    matched = locations[0]
    latitude = matched["latitude"]
    longitude = matched["longitude"]
    forecast = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "precipitation,weather_code,wind_speed_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,sunrise,sunset"
            ),
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=18,
    )
    forecast.raise_for_status()
    payload = forecast.json()
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    code = current.get("weather_code")
    if code is None:
        code = _first(daily.get("weather_code"))
    condition = _WEATHER_LABELS.get(code, f"天气代码 {code}")
    resolved_location = _display_location(matched) or normalized

    return "\n".join(
        [
            f"地点：{resolved_location}",
            f"观测/预报时间：{current.get('time') or _first(daily.get('time'))}",
            f"天气：{condition}",
            f"当前温度：{current.get('temperature_2m')}°C",
            f"体感温度：{current.get('apparent_temperature')}°C",
            f"相对湿度：{current.get('relative_humidity_2m')}%",
            f"当前降水：{current.get('precipitation')} mm",
            f"风速：{current.get('wind_speed_10m')} km/h",
            f"今日最高/最低：{_first(daily.get('temperature_2m_max'))}°C / "
            f"{_first(daily.get('temperature_2m_min'))}°C",
            "今日最高降水概率："
            f"{_first(daily.get('precipitation_probability_max'))}%",
            f"日出/日落：{_first(daily.get('sunrise'))} / "
            f"{_first(daily.get('sunset'))}",
            "数据来源：Open-Meteo（https://open-meteo.com/）",
        ]
    )
