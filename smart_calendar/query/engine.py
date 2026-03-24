"""查询引擎 — 按时间/类别/人物筛选日程"""

from __future__ import annotations

from datetime import date, timedelta

from smart_calendar.storage.event_store import Event, EventStore


class QueryEngine:
    """日程查询引擎"""

    def __init__(self, store: EventStore):
        self.store = store

    def by_date(self, dt: date) -> list[Event]:
        """查询某一天的日程"""
        return self.store.get(dt)

    def by_range(self, start: date, end: date) -> list[Event]:
        """查询日期范围内的日程"""
        return self.store.get_range(start, end)

    def upcoming(self, days: int = 7, from_date: date | None = None) -> list[Event]:
        """查询未来 N 天的日程"""
        if from_date is None:
            from_date = date.today()
        end = from_date + timedelta(days=days - 1)
        return self.by_range(from_date, end)

    def by_category(
        self,
        category: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Event]:
        """按类别筛选日程"""
        if start is None:
            start = date.today()
        if end is None:
            end = start + timedelta(days=30)
        events = self.by_range(start, end)
        return [e for e in events if e.category == category]

    def by_participant(
        self,
        name: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Event]:
        """按参与人筛选日程"""
        if start is None:
            start = date.today()
        if end is None:
            end = start + timedelta(days=30)
        events = self.by_range(start, end)
        return [e for e in events if name in e.participants]

    def search(self, keyword: str, start: date | None = None, end: date | None = None) -> list[Event]:
        """全文搜索标题和备注"""
        if start is None:
            start = date.today() - timedelta(days=30)
        if end is None:
            end = date.today() + timedelta(days=30)
        events = self.by_range(start, end)
        keyword_lower = keyword.lower()
        return [
            e
            for e in events
            if keyword_lower in e.title.lower()
            or keyword_lower in e.notes.lower()
            or keyword_lower in e.category.lower()
            or any(keyword_lower in p.lower() for p in e.participants)
        ]
