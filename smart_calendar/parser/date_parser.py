"""中文自然语言日期解析 — dateparser + pendulum"""

from __future__ import annotations

from datetime import datetime, date, time
from typing import Optional
import re

import dateparser
import pendulum


# pendulum 中文星期映射
_WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class DateParser:
    """中文日期/时间解析器"""

    def __init__(self, timezone: str = "Asia/Shanghai"):
        self.timezone = timezone

    def _now(self) -> pendulum.DateTime:
        return pendulum.now(self.timezone)

    def parse(self, text: str) -> datetime | None:
        """
        解析中文自然语言日期时间。

        支持:
          - "下周三下午3点"
          - "明天上午10点"
          - "3月28号14:00"
          - "后天晚上8点"
          - "2026-03-25 14:00"
          - "明天下午3点和张总开会讨论Q1进度"（从长句中提取日期）
        """
        # 策略1：先尝试完整文本
        result = self._try_dateparser(text)
        if result:
            return result

        # 策略2：分步提取日期词 + 时间词，组合解析
        result = self._parse_composite(text)
        if result:
            return result

        # 策略3：pendulum 解析标准格式
        try:
            return pendulum.parse(text, tz=self.timezone).naive()
        except Exception:
            pass

        return None

    def _try_dateparser(self, text: str) -> datetime | None:
        """调用 dateparser 解析"""
        return dateparser.parse(
            text,
            languages=["zh"],
            settings={
                "TIMEZONE": self.timezone,
                "RETURN_AS_TIMEZONE_AWARE": False,
                "PREFER_DATES_FROM": "future",
            },
        )

    def _parse_composite(self, text: str) -> datetime | None:
        """分步解析：先提取日期词，再提取时间词，组合成 datetime"""
        # 提取日期部分
        date_part = None
        date_patterns = [
            r"\d{4}[-/]\d{1,2}[-/]\d{1,2}",
            r"\d{1,2}月\d{1,2}[号日]?",
            r"(?:今天|明天|后天|大后天)",
            r"(?:这|本|下|上)周[一二三四五六日天]",
        ]
        for pattern in date_patterns:
            m = re.search(pattern, text)
            if m:
                date_part = m.group(0)
                break

        if not date_part:
            return None

        # 先尝试 dateparser
        dt = self._try_dateparser(date_part)

        # dateparser 解析失败时，手动处理常见中文日期词
        if not dt:
            dt = self._manual_date_parse(date_part)

        if not dt:
            return None

        # 提取时间部分
        time_patterns = [
            # "14:00" 格式
            (r"(\d{1,2}):(\d{2})", None),
            # "下午3点半"
            (r"(下午|晚上)(\d{1,2})[点时]半", "pm_half"),
            # "下午3点30分"
            (r"(下午|晚上)(\d{1,2})[点时](\d{1,2})分?", "pm_min"),
            # "下午3点"
            (r"(下午|晚上)(\d{1,2})[点时]", "pm"),
            # "上午10点半"
            (r"(上午|早上|中午)(\d{1,2})[点时]半", "am_half"),
            # "上午10点30分"
            (r"(上午|早上|中午)(\d{1,2})[点时](\d{1,2})分?", "am_min"),
            # "上午10点"
            (r"(上午|早上|中午)(\d{1,2})[点时]", "am"),
            # 没有上下午的 "3点半"
            (r"(\d{1,2})[点时]半", "bare_half"),
            # "3点30分"
            (r"(\d{1,2})[点时](\d{1,2})分?", "bare_min"),
            # "3点"
            (r"(\d{1,2})[点时]", "bare"),
        ]

        for pattern, mode in time_patterns:
            m = re.search(pattern, text)
            if m:
                groups = m.groups()
                if mode is None:
                    # HH:MM 格式
                    hour, minute = int(groups[0]), int(groups[1])
                elif mode == "pm_half":
                    hour, minute = int(groups[1]) + (12 if int(groups[1]) < 12 else 0), 30
                elif mode == "pm_min":
                    hour, minute = int(groups[1]) + (12 if int(groups[1]) < 12 else 0), int(groups[2])
                elif mode == "pm":
                    hour, minute = int(groups[1]) + (12 if int(groups[1]) < 12 else 0), 0
                elif mode == "am_half":
                    hour, minute = int(groups[1]), 30
                elif mode == "am_min":
                    hour, minute = int(groups[1]), int(groups[2])
                elif mode == "am":
                    hour, minute = int(groups[1]), 0
                elif mode == "bare_half":
                    hour, minute = int(groups[0]), 30
                elif mode == "bare_min":
                    hour, minute = int(groups[0]), int(groups[1])
                elif mode == "bare":
                    hour, minute = int(groups[0]), 0
                else:
                    continue
                return dt.replace(hour=hour, minute=minute)

        return dt

    def _manual_date_parse(self, text: str) -> datetime | None:
        """手动解析 dateparser 搞不定的中文日期词"""
        now = self._now()

        # 今天/明天/后天/大后天
        relative_days = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}
        for word, offset in relative_days.items():
            if word in text:
                dt = now.add(days=offset)
                return datetime(dt.year, dt.month, dt.day)

        # 下周X / 这周X / 上周X
        weekday_map = {
            "一": 0, "二": 1, "三": 2, "四": 3,
            "五": 4, "六": 5, "日": 6, "天": 6,
        }
        m = re.search(r"(这|本|下|上)周([一二三四五六日天])", text)
        if m:
            prefix, day_char = m.group(1), m.group(2)
            target_wd = weekday_map[day_char]
            current_wd = now.day_of_week  # pendulum: 0=Monday

            if prefix in ("这", "本"):
                diff = target_wd - current_wd
            elif prefix == "下":
                diff = target_wd - current_wd + 7
            elif prefix == "上":
                diff = target_wd - current_wd - 7
            else:
                diff = 0

            dt = now.add(days=diff)
            return datetime(dt.year, dt.month, dt.day)

        # X月X号/日
        m = re.search(r"(\d{1,2})月(\d{1,2})[号日]?", text)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            year = now.year
            return datetime(year, month, day)

        return None

    def parse_date_only(self, text: str) -> date | None:
        """只解析日期部分"""
        dt = self.parse(text)
        return dt.date() if dt else None

    def parse_time_only(self, text: str) -> str | None:
        """
        从文本中提取时间部分，返回 "HH:MM" 格式。

        支持:
          - "下午3点" → "15:00"
          - "14:00" → "14:00"
          - "上午10点半" → "10:30"
          - "14:00-15:30" → "14:00-15:30"
        """
        # 先检查 HH:MM-HH:MM 时间范围格式
        range_match = re.search(r"(\d{1,2}:\d{2})\s*[-–~到]\s*(\d{1,2}:\d{2})", text)
        if range_match:
            return f"{range_match.group(1)}-{range_match.group(2)}"

        # 检查单独的 HH:MM
        time_match = re.search(r"(\d{1,2}:\d{2})", text)
        if time_match:
            return time_match.group(1)

        # 用 dateparser 解析得到完整 datetime 后提取时间
        dt = self.parse(text)
        if dt and (dt.hour != 0 or dt.minute != 0):
            return f"{dt.hour:02d}:{dt.minute:02d}"

        return None

    def parse_range(self, text: str) -> tuple[date, date] | None:
        """
        解析时间范围表达。

        支持:
          - "这周" / "本周"
          - "这个月" / "本月"
          - "下周"
          - "3.20-3.31"
          - "3月20号到3月31号"
        """
        now = self._now()

        # 这周 / 本周
        if re.search(r"(这|本)周", text):
            start = now.start_of("week")
            end = now.end_of("week")
            return start.date(), end.date()

        # 下周
        if "下周" in text:
            next_week = now.add(weeks=1)
            start = next_week.start_of("week")
            end = next_week.end_of("week")
            return start.date(), end.date()

        # 上周
        if "上周" in text:
            last_week = now.subtract(weeks=1)
            start = last_week.start_of("week")
            end = last_week.end_of("week")
            return start.date(), end.date()

        # 这个月 / 本月
        if re.search(r"(这个?|本)月", text):
            start = now.start_of("month")
            end = now.end_of("month")
            return start.date(), end.date()

        # 下个月
        if re.search(r"下个?月", text):
            next_month = now.add(months=1)
            start = next_month.start_of("month")
            end = next_month.end_of("month")
            return start.date(), end.date()

        # X.XX-X.XX 或 X月XX号到X月XX号
        range_match = re.search(
            r"(\d{1,2})[./月](\d{1,2})[号日]?\s*[-–~到]\s*(\d{1,2})[./月](\d{1,2})[号日]?",
            text,
        )
        if range_match:
            m1, d1, m2, d2 = (int(x) for x in range_match.groups())
            year = now.year
            return date(year, m1, d1), date(year, m2, d2)

        return None

    def format_date(self, dt: date) -> str:
        """格式化日期为中文: "3月25日 周三" """
        weekday = _WEEKDAY_ZH[dt.weekday()]
        return f"{dt.month}月{dt.day}日 {weekday}"

    def format_datetime(self, dt: datetime) -> str:
        """格式化日期时间: "3月25日 周三 14:00" """
        date_str = self.format_date(dt.date() if isinstance(dt, datetime) else dt)
        if isinstance(dt, datetime) and (dt.hour != 0 or dt.minute != 0):
            return f"{date_str} {dt.hour:02d}:{dt.minute:02d}"
        return date_str
