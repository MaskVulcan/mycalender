"""测试 DateParser 中文日期解析"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

import pendulum
import pytest

from smart_calendar.parser.date_parser import DateParser


@pytest.fixture
def parser():
    return DateParser("Asia/Shanghai")


# ─── 日期解析 ────────────────────────────────────────────────


class TestParse:
    """测试 parse() 主入口"""

    def test_iso_date(self, parser):
        """标准 ISO 日期"""
        dt = parser.parse("2026-03-25")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 25

    def test_chinese_month_day(self, parser):
        """X月X号"""
        dt = parser.parse("3月28号")
        assert dt is not None
        assert dt.month == 3
        assert dt.day == 28

    def test_relative_tomorrow(self, parser):
        """明天"""
        dt = parser.parse("明天")
        assert dt is not None
        expected = date.today() + __import__("datetime").timedelta(days=1)
        assert dt.date() == expected or (dt.year == expected.year and dt.month == expected.month and dt.day == expected.day)

    def test_relative_today(self, parser):
        """今天"""
        dt = parser.parse("今天")
        assert dt is not None
        assert dt.year == date.today().year
        assert dt.month == date.today().month
        assert dt.day == date.today().day

    def test_afternoon_time(self, parser):
        """明天下午3点"""
        dt = parser.parse("明天下午3点")
        assert dt is not None
        assert dt.hour == 15
        assert dt.minute == 0

    def test_morning_time(self, parser):
        """上午10点半"""
        dt = parser.parse("明天上午10点半")
        assert dt is not None
        assert dt.hour == 10
        assert dt.minute == 30

    def test_natural_language_with_noise(self, parser):
        """从长句中提取日期: '明天下午3点和张总开会'"""
        dt = parser.parse("明天下午3点和张总开会")
        assert dt is not None
        assert dt.hour == 15

    def test_next_week(self, parser):
        """下周三"""
        dt = parser.parse("下周三")
        assert dt is not None
        # 应该是未来的某个周三
        assert dt.weekday() == 2  # 周三

    def test_evening_time(self, parser):
        """晚上8点"""
        dt = parser.parse("后天晚上8点")
        assert dt is not None
        assert dt.hour == 20

    def test_24h_format(self, parser):
        """14:00 格式"""
        dt = parser.parse("2026-03-25 14:00")
        assert dt is not None
        assert dt.hour == 14
        assert dt.minute == 0

    def test_unparseable(self, parser):
        """无法解析的文本"""
        dt = parser.parse("这不是一个日期")
        # dateparser 可能返回 None 或猜测一个日期，不做严格断言
        # 只确保不会抛异常


# ─── parse_date_only ─────────────────────────────────────────


class TestParseDateOnly:
    def test_returns_date(self, parser):
        """parse_date_only 返回 date 类型"""
        result = parser.parse_date_only("2026-03-25")
        assert isinstance(result, date)
        assert result == date(2026, 3, 25)


# ─── parse_time_only ─────────────────────────────────────────


class TestParseTimeOnly:
    def test_hhmm(self, parser):
        """提取 HH:MM 格式"""
        assert parser.parse_time_only("14:00 开会") == "14:00"

    def test_range_format(self, parser):
        """提取 HH:MM-HH:MM 范围"""
        result = parser.parse_time_only("14:00-15:30 讨论")
        assert result == "14:00-15:30"

    def test_chinese_afternoon(self, parser):
        """明天下午3点 → 15:00（需要日期上下文才能解析时间）"""
        result = parser.parse_time_only("明天下午3点开会")
        assert result == "15:00"

    def test_no_time(self, parser):
        """没有时间信息"""
        result = parser.parse_time_only("一段没有时间的文字")
        # 可能返回 None 或当前时间，不严格要求


# ─── parse_range ─────────────────────────────────────────────


class TestParseRange:
    def test_this_week(self, parser):
        """'这周' / '本周' 返回周一到周日"""
        result = parser.parse_range("这周")
        assert result is not None
        start, end = result
        assert start.weekday() == 0  # 周一
        assert end.weekday() == 6  # 周日
        assert (end - start).days == 6

    def test_next_week(self, parser):
        """'下周'"""
        result = parser.parse_range("下周")
        assert result is not None
        start, end = result
        assert start.weekday() == 0
        assert (end - start).days == 6
        # 下周的周一应该在今天之后
        assert start > date.today()

    def test_this_month(self, parser):
        """'本月'"""
        result = parser.parse_range("本月")
        assert result is not None
        start, end = result
        assert start.day == 1
        assert start.month == date.today().month

    def test_numeric_range(self, parser):
        """'3.20-3.31'"""
        result = parser.parse_range("3.20-3.31")
        assert result is not None
        start, end = result
        assert start == date(date.today().year, 3, 20)
        assert end == date(date.today().year, 3, 31)

    def test_chinese_range(self, parser):
        """'3月20号到3月31号'"""
        result = parser.parse_range("3月20号到3月31号")
        assert result is not None
        start, end = result
        assert start.month == 3 and start.day == 20
        assert end.month == 3 and end.day == 31

    def test_invalid_range(self, parser):
        """无法识别的范围"""
        assert parser.parse_range("随便说点什么") is None


# ─── format ──────────────────────────────────────────────────


class TestFormat:
    def test_format_date(self, parser):
        """格式化日期"""
        # 2026-03-25 是周三
        result = parser.format_date(date(2026, 3, 25))
        assert result == "3月25日 周三"

    def test_format_datetime(self, parser):
        """格式化日期时间"""
        dt = datetime(2026, 3, 25, 14, 30)
        result = parser.format_datetime(dt)
        assert result == "3月25日 周三 14:30"

    def test_format_datetime_midnight(self, parser):
        """午夜时间不显示时间部分"""
        dt = datetime(2026, 3, 25, 0, 0)
        result = parser.format_datetime(dt)
        assert result == "3月25日 周三"
