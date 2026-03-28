"""类别聚合统计 — 按类别统计频率、生成热力图数据"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

import pendulum

from smart_calendar.storage.event_store import Event
from smart_calendar.utils.constants import WEEKDAY_ZH


@dataclass
class AggResult:
    """聚合统计结果"""

    category: str
    period: str  # "2026年3月" / "3.23-3.29"
    total: int
    daily_counts: dict[date, int]  # {date: count} → 喂给 july 热力图
    avg_per_day: float
    peak_weekday: str  # "周三"
    peak_count: float  # 高峰日均次数
    active_days: int  # 有该事件的天数
    total_days: int  # 统计区间总天数


class Aggregator:
    """类别聚合引擎"""

    def __init__(self, timezone: str = "Asia/Shanghai"):
        self.timezone = timezone

    def get_period_range(self, period: str) -> tuple[date, date, str]:
        """获取周期的日期范围和显示标签。

        Args:
            period: "week" / "month" / "year"

        Returns:
            (start, end, label) 元组
        """
        now = pendulum.now(self.timezone)

        if period == "week":
            start = now.start_of("week").date()
            end = now.end_of("week").date()
            label = f"{start.month}.{start.day}-{end.month}.{end.day}"
        elif period == "month":
            start = now.start_of("month").date()
            end = now.end_of("month").date()
            label = f"{now.year}年{now.month}月"
        elif period == "year":
            start = now.start_of("year").date()
            end = now.end_of("year").date()
            label = f"{now.year}年"
        else:
            # 默认本月
            start = now.start_of("month").date()
            end = now.end_of("month").date()
            label = f"{now.year}年{now.month}月"

        return start, end, label

    def summary(self, events: list[Event], category: str, period: str = "month") -> AggResult:
        """计算某类别在指定周期内的聚合统计"""
        start, end, label = self.get_period_range(period)

        # 筛选该类别 + 时间范围内的事件
        filtered = [
            e for e in events if e.category == category and start <= e.date <= end
        ]

        # 按天统计次数
        daily = Counter(e.date for e in filtered)

        # 填充完整日期范围（没有事件的天数为 0）
        total_days = (end - start).days + 1
        all_days = {start + timedelta(days=i): 0 for i in range(total_days)}
        all_days.update(daily)

        # 按星期几统计，找高峰日
        weekday_counts: dict[int, list[int]] = {i: [] for i in range(7)}
        for d, count in all_days.items():
            weekday_counts[d.weekday()].append(count)

        peak_weekday_idx = 0
        peak_avg = 0.0
        for wd, counts in weekday_counts.items():
            if counts:
                avg = sum(counts) / len(counts)
                if avg > peak_avg:
                    peak_avg = avg
                    peak_weekday_idx = wd

        active_days = len(daily)  # Counter 只含 > 0 的条目
        total = len(filtered)
        avg = total / total_days if total_days > 0 else 0

        return AggResult(
            category=category,
            period=label,
            total=total,
            daily_counts=all_days,
            avg_per_day=round(avg, 2),
            peak_weekday=WEEKDAY_ZH[peak_weekday_idx],
            peak_count=round(peak_avg, 2),
            active_days=active_days,
            total_days=total_days,
        )

    def compare(
        self, events: list[Event], categories: list[str], period: str = "month"
    ) -> list[AggResult]:
        """多类别对比"""
        return [self.summary(events, cat, period) for cat in categories]
