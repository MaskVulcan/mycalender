"""测试日程冲突检测"""

from __future__ import annotations

from datetime import date

import pytest

from smart_calendar.storage.event_store import Event, EventStore


@pytest.fixture
def store(tmp_path):
    return EventStore(tmp_path / "events")


class TestParseTimeRange:
    """测试 _parse_time_range 静态方法"""

    def test_single_time(self):
        """14:00 → (840, 900)  默认 1 小时"""
        start, end = EventStore._parse_time_range("14:00")
        assert start == 14 * 60
        assert end == 14 * 60 + 60

    def test_time_range(self):
        """14:00-15:30 → (840, 930)"""
        start, end = EventStore._parse_time_range("14:00-15:30")
        assert start == 14 * 60
        assert end == 15 * 60 + 30

    def test_morning(self):
        """09:00-10:00"""
        start, end = EventStore._parse_time_range("09:00-10:00")
        assert start == 9 * 60
        assert end == 10 * 60

    def test_invalid_format(self):
        """无效格式返回 None"""
        start, end = EventStore._parse_time_range("无效")
        assert start is None
        assert end is None


class TestFindConflicts:
    """测试 find_conflicts 冲突检测"""

    def test_no_conflict_different_time(self, store):
        """不同时段无冲突"""
        dt = date(2026, 3, 25)
        store.add(Event(id="", date=dt, time="09:00-10:00", title="晨会"))
        conflicts = store.find_conflicts(dt, "14:00-15:00")
        assert conflicts == []

    def test_overlap_conflict(self, store):
        """时间段重叠"""
        dt = date(2026, 3, 25)
        store.add(Event(id="", date=dt, time="14:00-15:00", title="会议A"))
        conflicts = store.find_conflicts(dt, "14:30-15:30")
        assert len(conflicts) == 1
        assert conflicts[0].title == "会议A"

    def test_contained_conflict(self, store):
        """新时段完全包含在已有时段内"""
        dt = date(2026, 3, 25)
        store.add(Event(id="", date=dt, time="13:00-16:00", title="长会"))
        conflicts = store.find_conflicts(dt, "14:00-15:00")
        assert len(conflicts) == 1

    def test_exact_same_time(self, store):
        """完全相同的时间段"""
        dt = date(2026, 3, 25)
        store.add(Event(id="", date=dt, time="14:00-15:00", title="会议A"))
        conflicts = store.find_conflicts(dt, "14:00-15:00")
        assert len(conflicts) == 1

    def test_adjacent_no_conflict(self, store):
        """首尾相接不算冲突"""
        dt = date(2026, 3, 25)
        store.add(Event(id="", date=dt, time="14:00-15:00", title="会议A"))
        conflicts = store.find_conflicts(dt, "15:00-16:00")
        assert conflicts == []

    def test_multiple_conflicts(self, store):
        """多个冲突"""
        dt = date(2026, 3, 25)
        store.add(Event(id="", date=dt, time="14:00-15:00", title="会议A"))
        store.add(Event(id="", date=dt, time="14:30-16:00", title="会议B"))
        conflicts = store.find_conflicts(dt, "14:00-16:00")
        assert len(conflicts) == 2

    def test_no_events_no_conflict(self, store):
        """空日期无冲突"""
        conflicts = store.find_conflicts(date(2026, 3, 25), "14:00")
        assert conflicts == []

    def test_single_time_default_1h(self, store):
        """单时间点默认 1 小时范围"""
        dt = date(2026, 3, 25)
        store.add(Event(id="", date=dt, time="14:30-15:30", title="会议A"))
        # 14:00 默认到 15:00，与 14:30-15:30 重叠
        conflicts = store.find_conflicts(dt, "14:00")
        assert len(conflicts) == 1
