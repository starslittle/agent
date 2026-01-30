from __future__ import annotations

from typing import Optional, Tuple

from langchain_core.tools import tool


def _parse_date(date_str: str) -> Tuple[int, int, int]:
    if not date_str:
        raise ValueError("birth_date 不能为空，格式应为 YYYY-MM-DD")
    parts = date_str.strip().replace("/", "-").split("-")
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


def _safe_call(fn, default: str = "") -> str:
    try:
        return fn()
    except Exception:
        return default


@tool
def get_lunar_chart(
    birth_date: str,
    birth_time: str = "00:00",
    gender: Optional[str] = None,
    birthplace: Optional[str] = None,
) -> str:
    """
    使用 lunar-python 生成命理排盘信息（公历/农历/八字）。

    参数:
    - birth_date: 公历日期，格式 YYYY-MM-DD
    - birth_time: 公历时间，格式 HH:MM 或 HH:MM:SS，默认 00:00
    - gender: 性别，可选
    - birthplace: 出生地（城市），可选
    """
    try:
        from lunar_python import Solar, Lunar  # type: ignore
    except Exception as e:
        raise RuntimeError(f"lunar_python 未安装或导入失败: {e}")

    y, m, d = _parse_date(birth_date)
    hh, mm, ss = _parse_time(birth_time)

    solar = None
    lunar = None

    # 优先使用 Solar 构建（带时间）
    if hasattr(Solar, "fromYmdHms"):
        solar = Solar.fromYmdHms(y, m, d, hh, mm, ss)
        lunar = solar.getLunar()
    elif hasattr(Lunar, "fromYmdHms"):
        lunar = Lunar.fromYmdHms(y, m, d, hh, mm, ss)
        solar = lunar.getSolar()
    elif hasattr(Solar, "fromYmd"):
        solar = Solar.fromYmd(y, m, d)
        lunar = solar.getLunar()
    elif hasattr(Lunar, "fromYmd"):
        lunar = Lunar.fromYmd(y, m, d)
        solar = lunar.getSolar()
    else:
        raise RuntimeError("lunar_python 版本不支持当前构建方式")

    solar_text = _safe_call(solar.toFullString, "")
    lunar_text = _safe_call(lunar.toFullString, "")

    eight_char = _safe_call(lunar.getEightChar, None)
    if eight_char:
        year_gz = _safe_call(eight_char.getYear, "")
        month_gz = _safe_call(eight_char.getMonth, "")
        day_gz = _safe_call(eight_char.getDay, "")
        time_gz = _safe_call(eight_char.getTime, "")
        bazi = f"{year_gz} {month_gz} {day_gz} {time_gz}".strip()
    else:
        bazi = ""

    animal = _safe_call(lunar.getAnimal, "")

    lines = [
        "【排盘结果】",
        f"- 公历: {solar_text or f'{y}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d}'}",
        f"- 农历: {lunar_text}" if lunar_text else "- 农历: (未获取)",
        f"- 生肖: {animal}" if animal else "- 生肖: (未获取)",
        f"- 八字: {bazi}" if bazi else "- 八字: (未获取)",
    ]

    if gender:
        lines.append(f"- 性别: {gender}")
    if birthplace:
        lines.append(f"- 出生地: {birthplace}")

    return "\n".join(lines)
