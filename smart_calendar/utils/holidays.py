"""中国节假日封装 — 基于 chinese-calendar"""

from __future__ import annotations

from datetime import date, timedelta

from chinese_calendar import (
    is_holiday,
    is_workday,
    is_in_lieu,
    get_holiday_detail,
)


# 节假日名称翻译
_HOLIDAY_NAMES = {
    "New Year's Day": "元旦",
    "Spring Festival": "春节",
    "Tomb-sweeping Day": "清明节",
    "Labour Day": "劳动节",
    "Dragon Boat Festival": "端午节",
    "Mid-autumn Festival": "中秋节",
    "National Day": "国庆节",
}


def get_day_type(dt: date) -> str:
    """
    获取某天的类型。

    Returns:
        "holiday" — 法定假日
        "in_lieu" — 调休（补班）
        "weekend" — 普通周末
        "workday" — 工作日
    """
    try:
        if is_in_lieu(dt):
            # 调休补班日：该休息却要上班（is_workday=True, is_holiday=False）
            return "in_lieu"
        elif is_holiday(dt):
            return "holiday"
        elif is_workday(dt):
            return "workday"
        else:
            return "weekend"
    except Exception:
        # chinese-calendar 不支持的年份，降级为简单周末判断
        if dt.weekday() >= 5:
            return "weekend"
        return "workday"


def get_holiday_name(dt: date) -> str | None:
    """获取节假日名称（中文），非假日返回 None"""
    try:
        on_holiday, holiday_name = get_holiday_detail(dt)
        if on_holiday and holiday_name:
            name_str = str(holiday_name)
            # 尝试翻译
            return _HOLIDAY_NAMES.get(name_str, name_str)
        return None
    except Exception:
        return None


def get_day_label(dt: date) -> str:
    """
    获取某天的简短标签，用于日历展示。

    Returns:
        "" — 普通工作日
        "🔴 假" — 法定假日
        "🔵 班" — 调休补班
        "休" — 普通周末
    """
    day_type = get_day_type(dt)
    if day_type == "holiday":
        name = get_holiday_name(dt)
        if name:
            return f"🔴 {name}"
        return "🔴 假"
    elif day_type == "in_lieu":
        return "🔵 班"
    elif day_type == "weekend":
        return "休"
    return ""


def get_month_holidays(year: int, month: int) -> list[dict]:
    """
    获取某月的节假日/调休信息。

    Returns:
        [{"date": date, "type": str, "name": str | None}, ...]
    """
    from calendar import monthrange

    _, days = monthrange(year, month)
    result = []
    for day in range(1, days + 1):
        dt = date(year, month, day)
        day_type = get_day_type(dt)
        if day_type in ("holiday", "in_lieu"):
            result.append(
                {
                    "date": dt,
                    "type": day_type,
                    "name": get_holiday_name(dt),
                }
            )
    return result


def get_upcoming_holidays(from_date: date | None = None, days: int = 90) -> list[dict]:
    """获取未来 N 天内的节假日"""
    if from_date is None:
        from_date = date.today()

    result = []
    seen_names = set()
    for i in range(days):
        dt = from_date + timedelta(days=i)
        day_type = get_day_type(dt)
        if day_type == "holiday":
            name = get_holiday_name(dt)
            if name and name not in seen_names:
                seen_names.add(name)
                result.append({"date": dt, "name": name})
    return result
