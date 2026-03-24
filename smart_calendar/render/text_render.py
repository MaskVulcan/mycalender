"""终端文字渲染 — 基于 Rich"""

from __future__ import annotations

from datetime import date
from itertools import groupby

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from smart_calendar.storage.event_store import Event
from smart_calendar.query.aggregator import AggResult
from smart_calendar.utils.config import Config


_WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# priority 样式
_PRIORITY_STYLE = {
    "high": "bold red",
    "normal": "",
    "low": "dim",
}


class TextRender:
    """Rich 终端渲染器"""

    def __init__(self, config: Config | None = None):
        self.console = Console()
        self.config = config or Config()

    def render_schedule(self, events: list[Event], title: str = "📅 近期安排"):
        """渲染日程列表表格"""
        if not events:
            self.console.print(Panel("[dim]暂无日程[/dim]", title=title))
            return

        table = Table(title=title, show_lines=True, border_style="blue")
        table.add_column("日期", style="cyan", width=12, no_wrap=True)
        table.add_column("时间", style="green", width=13, no_wrap=True)
        table.add_column("事件", min_width=16)
        table.add_column("参与人", style="yellow", width=14)
        table.add_column("备注", style="dim", max_width=24)

        # 按日期分组
        events_sorted = sorted(events, key=lambda e: (e.date, e.start_hour, e.start_minute))

        last_date = None
        for event in events_sorted:
            # 日期列：同一天只显示第一次
            if event.date != last_date:
                weekday = _WEEKDAY_ZH[event.date.weekday()]
                date_str = f"{event.date.month}.{event.date.day} {weekday}"
                last_date = event.date
            else:
                date_str = ""

            # 类别图标 + 标题
            icon = self.config.get_category_icon(event.category)
            title_str = f"{icon} {event.title}"

            # priority 样式
            style = _PRIORITY_STYLE.get(event.priority, "")

            # 参与人
            people = ", ".join(event.participants) if event.participants else ""

            # 备注截断
            notes = event.notes[:20] + "…" if len(event.notes) > 20 else event.notes

            table.add_row(date_str, event.time, title_str, people, notes, style=style)

        self.console.print(table)

    def render_stats(self, result: AggResult):
        """渲染类别聚合统计"""
        icon = self.config.get_category_icon(result.category)

        table = Table(
            title=f"📊 {result.period}「{result.category}」统计",
            show_lines=True,
            border_style="magenta",
        )
        table.add_column("维度", style="bold", width=10)
        table.add_column("数值", style="cyan", width=8, justify="right")
        table.add_column("详情", style="dim", min_width=16)

        table.add_row("本期总计", f"{result.total} 次", result.period)
        table.add_row("日均", f"{result.avg_per_day} 次", f"有事天数 {result.active_days} 天")
        table.add_row("高峰日", result.peak_weekday, f"平均 {result.peak_count} 次")
        table.add_row(
            "活跃率",
            f"{result.active_days}/{result.total_days}",
            f"{result.active_days / result.total_days * 100:.0f}%" if result.total_days else "N/A",
        )

        self.console.print(table)

    def render_compare(self, results: list[AggResult]):
        """渲染多类别对比"""
        if not results:
            self.console.print("[dim]暂无数据[/dim]")
            return

        table = Table(
            title=f"📊 类别对比 — {results[0].period}",
            show_lines=True,
            border_style="magenta",
        )
        table.add_column("类别", style="bold", width=10)
        table.add_column("总次数", style="cyan", width=8, justify="right")
        table.add_column("日均", width=8, justify="right")
        table.add_column("活跃天", width=8, justify="right")
        table.add_column("高峰日", width=8)

        for r in sorted(results, key=lambda x: x.total, reverse=True):
            icon = self.config.get_category_icon(r.category)
            table.add_row(
                f"{icon} {r.category}",
                f"{r.total}",
                f"{r.avg_per_day}",
                f"{r.active_days}/{r.total_days}",
                r.peak_weekday,
            )

        self.console.print(table)
