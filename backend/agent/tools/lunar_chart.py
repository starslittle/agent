from __future__ import annotations

from typing import Optional, Tuple

def _parse_date(date_str: str) -> Tuple[int, int, int]:
    if not date_str:
        raise ValueError("birth_date 不能为空，格式应为 YYYY-MM-DD")
    raw = date_str.strip()
    if not raw:
        raise ValueError("birth_date 不能为空，格式应为 YYYY-MM-DD")

    # 兼容常见格式：YYYYMMDD / YYYY年MM月DD日 / YYYY/MM/DD
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


def _safe_call(fn, default: str = "") -> str:
    try:
        return fn()
    except Exception:
        return default


def _normalize_gender(gender: Optional[str]) -> Optional[int]:
    if not gender:
        return None
    g = str(gender).strip().lower()
    if g in {"男", "male", "m", "1", "man", "boy"}:
        return 1
    if g in {"女", "female", "f", "0", "woman", "girl"}:
        return 0
    return None


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
            # 保持原始输入，交给下游解析报错
            pass

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

    # 大运（如 lunar_python 支持且可获取）
    da_yun_items = []
    if eight_char and hasattr(eight_char, "getYun"):
        yun = None
        gender_flag = _normalize_gender(gender)
        try:
            yun = eight_char.getYun() if gender_flag is None else eight_char.getYun(gender_flag)
        except TypeError:
            if gender_flag is not None:
                for val in (gender_flag, "男" if gender_flag == 1 else "女", "M" if gender_flag == 1 else "F"):
                    try:
                        yun = eight_char.getYun(val)
                        break
                    except Exception:
                        continue
        except Exception:
            yun = None

        if yun is not None and hasattr(yun, "getDaYun"):
            try:
                da_yun_items = yun.getDaYun() or []
            except Exception:
                da_yun_items = []

    if da_yun_items:
        lines.append("- 大运:")
        for dy in da_yun_items[:12]:
            name = ""
            if hasattr(dy, "getName"):
                name = _safe_call(dy.getName, "")
            elif hasattr(dy, "getGanZhi"):
                name = _safe_call(dy.getGanZhi, "")
            elif hasattr(dy, "getZhi"):
                name = _safe_call(dy.getZhi, "")
            elif hasattr(dy, "getStartYear") or hasattr(dy, "getEndYear"):
                name = ""
            else:
                name = str(dy).strip()

            start_age = _safe_call(dy.getStartAge, "") if hasattr(dy, "getStartAge") else ""
            end_age = _safe_call(dy.getEndAge, "") if hasattr(dy, "getEndAge") else ""
            start_year = _safe_call(dy.getStartYear, "") if hasattr(dy, "getStartYear") else ""
            end_year = _safe_call(dy.getEndYear, "") if hasattr(dy, "getEndYear") else ""
            parts = []
            if name:
                parts.append(str(name))
            if start_age or end_age:
                if start_age and end_age:
                    parts.append(f"{start_age}-{end_age}岁")
                elif start_age:
                    parts.append(f"{start_age}岁")
                else:
                    parts.append(f"{end_age}岁")
            if start_year or end_year:
                if start_year and end_year:
                    parts.append(f"{start_year}-{end_year}")
                elif start_year:
                    parts.append(str(start_year))
                else:
                    parts.append(str(end_year))
            if parts:
                lines.append("  - " + " | ".join(parts))

    return "\n".join(lines)
