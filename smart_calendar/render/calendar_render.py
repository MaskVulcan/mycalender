"""日历图渲染 — TOAST UI Calendar + Playwright 截图"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from smart_calendar.storage.event_store import Event
from smart_calendar.utils.config import Config


# 视图 → TOAST UI view name
_VIEW_MAP = {
    "month": "month",
    "week": "week",
    "day": "day",
}

# 视图 → 默认截图尺寸
_SIZE_MAP = {
    "month": {"width": 1200, "height": 900},
    "week": {"width": 1200, "height": 1200},
    "day": {"width": 900, "height": 1000},
}


class CalendarRender:
    """TOAST UI Calendar → PNG 渲染器"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))

    def _build_event_data(self, events: list[Event]) -> list[dict]:
        """将 Event 转为模板需要的 dict 格式"""
        result = []
        for e in events:
            icon = self.config.get_category_icon(e.category)

            # 解析 start/end ISO 时间
            time_parts = e.time.split("-")
            start_time = time_parts[0].strip()
            end_time = time_parts[1].strip() if len(time_parts) > 1 else None

            # 构建 start datetime
            h, m = (int(x) for x in start_time.split(":"))
            start_dt = datetime(e.date.year, e.date.month, e.date.day, h, m)

            # 构建 end datetime（默认 1 小时）
            if end_time:
                eh, em = (int(x) for x in end_time.split(":"))
                end_dt = datetime(e.date.year, e.date.month, e.date.day, eh, em)
            else:
                end_dt = start_dt + timedelta(hours=1)

            result.append(
                {
                    "id": e.id,
                    "category": e.category,
                    "icon": icon,
                    "title": e.title,
                    "start_iso": start_dt.isoformat(),
                    "end_iso": end_dt.isoformat(),
                    "location": e.location,
                    "participants": e.participants,
                }
            )
        return result

    def render_html(
        self,
        events: list[Event],
        view: str = "week",
        focus_date: date | None = None,
        title: str = "Smart Calendar",
        date_range: str = "",
    ) -> str:
        """渲染 HTML 字符串"""
        if focus_date is None:
            focus_date = date.today()

        tui_view = _VIEW_MAP.get(view, "week")
        size = _SIZE_MAP.get(view, _SIZE_MAP["week"])

        # 动态计算小时范围：覆盖所有事件
        work_start, work_end = self.config.work_hours
        hour_start = work_start
        hour_end = work_end + 1

        for e in events:
            if e.start_hour > 0:
                hour_start = min(hour_start, e.start_hour)
                # 事件结束至少 +1 小时余量
                time_parts = e.time.split("-")
                if len(time_parts) > 1:
                    try:
                        end_h = int(time_parts[1].strip().split(":")[0])
                        hour_end = max(hour_end, end_h + 1)
                    except ValueError:
                        hour_end = max(hour_end, e.start_hour + 2)
                else:
                    hour_end = max(hour_end, e.start_hour + 2)

        hour_end = min(hour_end, 24)  # 上限 24

        # 根据时间跨度动态计算高度（每小时约 80px，最少 600px）
        hour_span = hour_end - hour_start
        cal_height = max(600, hour_span * 80)

        template = self.env.get_template("toast_ui.html")
        html = template.render(
            title=title,
            date_range=date_range,
            view=tui_view,
            focus_date=focus_date.isoformat(),
            events=self._build_event_data(events),
            categories=self.config.categories,
            height=cal_height,
            hour_start=hour_start,
            hour_end=hour_end,
        )
        return html

    def render_png(
        self,
        events: list[Event],
        output_path: str | Path,
        view: str = "week",
        focus_date: date | None = None,
        title: str = "Smart Calendar",
        date_range: str = "",
    ) -> Path:
        """渲染日历图为 PNG 文件"""
        from playwright.sync_api import sync_playwright

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html = self.render_html(events, view, focus_date, title, date_range)
        size = _SIZE_MAP.get(view, _SIZE_MAP["week"])

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": size["width"], "height": size["height"]},
                device_scale_factor=2,
            )
            page.set_content(html)
            # 等待 TOAST UI Calendar 渲染完成（DOM 元素就绪）
            try:
                page.wait_for_selector(
                    ".toastui-calendar-layout",
                    state="attached",
                    timeout=10000,
                )
                # 额外等待短暂时间确保事件渲染到位
                page.wait_for_timeout(500)
            except Exception:
                # fallback: 如果选择器未找到，等待固定时间
                page.wait_for_timeout(3000)
            page.screenshot(path=str(output_path), full_page=True)
            browser.close()

        return output_path
