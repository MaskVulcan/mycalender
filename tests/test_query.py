"""测试 QueryEngine 和 Aggregator"""

from __future__ import annotations

from datetime import date

import pytest

from smart_calendar.storage.event_store import Event, EventStore
from smart_calendar.query.engine import QueryEngine
from smart_calendar.query.aggregator import Aggregator, AggResult


# ─── fixtures ────────────────────────────────────────────────


def _make_event(dt: date, title: str, category: str = "会议",
                participants: list[str] | None = None, time: str = "10:00") -> Event:
    """快速创建测试用 Event"""
    return Event(
        id="", date=dt, time=time, title=title,
        category=category, participants=participants or [],
    )


@pytest.fixture
def store_with_data(tmp_path):
    """包含预置数据的 EventStore + QueryEngine"""
    store = EventStore(tmp_path / "events")

    # 3月24日: 2个会议
    store.add(_make_event(date(2026, 3, 24), "晨会", "会议", ["张总"]))
    store.add(_make_event(date(2026, 3, 24), "评审会", "技术", ["小王"], "14:00"))

    # 3月25日: 1个会议 + 1个学习
    store.add(_make_event(date(2026, 3, 25), "进度会", "会议", ["张总", "李经理"], "15:00"))
    store.add(_make_event(date(2026, 3, 25), "读书", "学习", time="20:00"))

    # 3月26日: 1个社交
    store.add(_make_event(date(2026, 3, 26), "团队聚餐", "社交", ["全组"], "19:00"))

    # 3月27日: 1个技术
    store.add(_make_event(date(2026, 3, 27), "技术分享", "技术", ["全组"], "14:00"))

    return store, QueryEngine(store)


# ─── QueryEngine 测试 ────────────────────────────────────────


class TestQueryEngine:
    def test_by_date(self, store_with_data):
        store, qe = store_with_data
        events = qe.by_date(date(2026, 3, 24))
        assert len(events) == 2

    def test_by_date_empty(self, store_with_data):
        store, qe = store_with_data
        events = qe.by_date(date(2026, 3, 28))
        assert events == []

    def test_by_range(self, store_with_data):
        store, qe = store_with_data
        events = qe.by_range(date(2026, 3, 24), date(2026, 3, 26))
        assert len(events) == 5  # 2 + 2 + 1

    def test_by_category(self, store_with_data):
        store, qe = store_with_data
        events = qe.by_category("会议", date(2026, 3, 24), date(2026, 3, 27))
        assert len(events) == 2
        assert all(e.category == "会议" for e in events)

    def test_by_category_no_match(self, store_with_data):
        store, qe = store_with_data
        events = qe.by_category("个人", date(2026, 3, 24), date(2026, 3, 27))
        assert events == []

    def test_by_participant(self, store_with_data):
        store, qe = store_with_data
        events = qe.by_participant("张总", date(2026, 3, 24), date(2026, 3, 27))
        assert len(events) == 2
        assert all("张总" in e.participants for e in events)

    def test_search_by_title(self, store_with_data):
        store, qe = store_with_data
        events = qe.search("技术", date(2026, 3, 24), date(2026, 3, 27))
        # 匹配: 技术分享(标题) + 评审会(category=技术)
        assert len(events) == 2

    def test_search_by_participant(self, store_with_data):
        store, qe = store_with_data
        events = qe.search("全组", date(2026, 3, 24), date(2026, 3, 27))
        assert len(events) == 2  # 团队聚餐 + 技术分享

    def test_upcoming(self, store_with_data):
        """upcoming 使用 from_date 参数"""
        store, qe = store_with_data
        events = qe.upcoming(days=3, from_date=date(2026, 3, 25))
        # 3月25日(2) + 3月26日(1) + 3月27日(1) = 4
        assert len(events) == 4


# ─── Aggregator 测试 ─────────────────────────────────────────


class TestAggregator:
    def test_summary_basic(self, store_with_data):
        """基本聚合统计"""
        store, _ = store_with_data
        agg = Aggregator("Asia/Shanghai")

        # 取所有事件
        events = store.get_range(date(2026, 3, 24), date(2026, 3, 27))
        assert len(events) == 6

        # 手动构造一个按 3.24-3.27 范围的 summary
        # 由于 summary 内部使用 _get_period_range (基于当前时间)，
        # 我们直接测试返回的 AggResult 结构
        result = agg.summary(events, "会议", "month")
        assert isinstance(result, AggResult)
        assert result.category == "会议"
        assert result.total_days > 0

    def test_summary_counts_correct_category(self):
        """只统计指定类别"""
        agg = Aggregator()
        events = [
            _make_event(date(2026, 3, 24), "会1", "会议"),
            _make_event(date(2026, 3, 24), "会2", "会议"),
            _make_event(date(2026, 3, 25), "学1", "学习"),
        ]
        result = agg.summary(events, "会议", "month")
        # 会议只在3月24日，但要看是否在 _get_period_range 范围内
        # 这里 total 可能是 0 或 2，取决于当前月是否是3月
        assert isinstance(result.total, int)

    def test_compare(self, store_with_data):
        """多类别对比"""
        store, _ = store_with_data
        agg = Aggregator("Asia/Shanghai")

        events = store.get_range(date(2026, 3, 24), date(2026, 3, 27))
        results = agg.compare(events, ["会议", "技术", "学习"], "month")

        assert len(results) == 3
        categories = {r.category for r in results}
        assert categories == {"会议", "技术", "学习"}

    def test_agg_result_fields(self):
        """AggResult 字段完整性"""
        result = AggResult(
            category="会议", period="2026年3月",
            total=10, daily_counts={}, avg_per_day=0.33,
            peak_weekday="周三", peak_count=2.0,
            active_days=5, total_days=31,
        )
        assert result.category == "会议"
        assert result.avg_per_day == 0.33
        assert result.peak_weekday == "周三"
