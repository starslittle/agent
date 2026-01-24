from __future__ import annotations

from typing import Optional, Tuple

from langchain_core.tools import tool


def _parse_date(date_str: str) -> Tuple[int, int, int]:
    if not date_str:
        raise ValueError("birth_date 不能为空，格式应为 YYYY-MM-DD")
    raw = date_str.strip()
    if not raw:
        raise ValueError("birth_date 不能为空，格式应为 YYYY-MM-DD")

    normalized = (
        raw.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("/", "-")
    )
    if normalized.isdigit() and len(normalized) == 8:
        normalized = f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:]}"

    parts = [p for p in normalized.split("-") if p]
    if len(parts) != 3:
        raise ValueError("birth_date 格式错误，应为 YYYY-MM-DD")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _parse_time(time_str: Optional[str]) -> Tuple[int, int, int]:
    if not time_str:
        return 0, 0, 0
    t = time_str.strip()
    if not t:
        return 0, 0, 0
    parts = t.split(":")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1]), 0
    if len(parts) == 3:
        return int(parts[0]), int(parts[1]), int(parts[2])
    raise ValueError("birth_time 格式错误，应为 HH:MM 或 HH:MM:SS")


def _normalize_gender(gender: Optional[str]) -> Optional[str]:
    if not gender:
        return None
    g = str(gender).strip().lower()
    if g in {"男", "male", "m", "1", "man", "boy"}:
        return "男"
    if g in {"女", "female", "f", "0", "woman", "girl"}:
        return "女"
    return None


def _time_index_from_hms(hour: int, minute: int, second: int) -> int:
    if hour < 0 or hour > 23 or minute < 0 or minute > 59 or second < 0 or second > 59:
        raise ValueError("birth_time 超出合法范围")
    if hour == 23:
        return 0  # 早子时 23:00-23:59
    if hour == 0:
        return 12  # 晚子时 00:00-00:59
    # 01:00-22:59 -> 丑到亥
    return (hour + 1) // 2


@tool
def get_ziwei_chart(
    birth_date: str,
    birth_time: str = "00:00",
    gender: Optional[str] = None,
    birthplace: Optional[str] = None,
) -> str:
    """
    使用 py-iztro 生成紫微斗数排盘信息（命盘、十二宫）。

    参数:
    - birth_date: 公历日期，格式 YYYY-MM-DD
    - birth_time: 公历时间，格式 HH:MM 或 HH:MM:SS，默认 00:00
    - gender: 性别（男/女），必填
    - birthplace: 出生地（城市），可选
    """
    # 容错：当 Action Input 被当作字符串传入时，尝试从 JSON 中解析字段
    if isinstance(birth_date, str) and birth_date.strip().startswith("{"):
        try:
            import json

            payload = json.loads(birth_date)
            if isinstance(payload, dict):
                birth_date = payload.get("birth_date", birth_date)
                birth_time = payload.get("birth_time", birth_time)
                gender = payload.get("gender", gender)
                birthplace = payload.get("birthplace", birthplace)
        except Exception:
            pass

    try:
        from py_iztro import Astro  # type: ignore
    except Exception as e:
        raise RuntimeError(f"py-iztro 未安装或导入失败: {e}")

    y, m, d = _parse_date(birth_date)
    hh, mm, ss = _parse_time(birth_time)
    gender_norm = _normalize_gender(gender)
    if not gender_norm:
        raise ValueError("gender 不能为空，且需为 男/女")

    time_index = _time_index_from_hms(hh, mm, ss)
    astro = Astro()
    chart = astro.by_solar(f"{y}-{m}-{d}", time_index, gender_norm, fix_leap=True, language="zh-CN")

    lines = [
        "【紫微斗数排盘】",
        f"- 公历: {chart.solar_date}",
        f"- 农历: {chart.lunar_date}",
        f"- 农历中文: {chart.chinese_date}",
        f"- 时辰: {chart.time} ({chart.time_range})",
        f"- 生肖: {chart.zodiac}",
        f"- 星座: {chart.sign}",
        f"- 五行局: {chart.five_elements_class}",
        f"- 命宫: {chart.soul}",
        f"- 身宫: {chart.body}",
        f"- 性别: {chart.gender}",
    ]
    if birthplace:
        lines.append(f"- 出生地: {birthplace}")

    lines.append("- 十二宫主星:")
    for palace in chart.palaces:
        stem_branch = f"{palace.heavenly_stem}{palace.earthly_branch}"
        major = [s.name for s in (palace.major_stars or [])]
        major_text = "、".join(major) if major else "无主星"
        suffix = []
        if palace.is_body_palace:
            suffix.append("身宫")
        if palace.is_original_palace:
            suffix.append("原局")
        suffix_text = f"（{','.join(suffix)}）" if suffix else ""
        lines.append(f"  - {palace.name}{suffix_text}({stem_branch}): {major_text}")

    return "\n".join(lines)
