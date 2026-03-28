"""测试 CalendarRender 的纯逻辑部分（不启动 Playwright）"""

from __future__ import annotations

from datetime import date

import pytest

from smart_calendar.storage.event_store import Event
from smart_calendar.render.calendar_render import CalendarRender
from smart_calendar.utils.config import Config


@pytest.fixture
def render(tmp_path):
    """创建一个 CalendarRender 实例"""
    config_dir = tmp_path / "data"
    config_dir.mkdir()
    config_file = config_dir / "config.yml"
    config_file.write_text("""
categories:
  会议:
    color: "#FF6B35"
    icon: "🤝"
    heatmap_cmap: "Oranges"
  技术:
    color: "#4ECDC4"
    icon: "💻"
    heatmap_cmap: "Blues"
  其他:
    color: "#DFE6E9"
    icon: "📌"
    heatmap_cmap: "Greys"

defaults:
  timezone: "Asia/Shanghai"
  data_dir: "./data"
  output_dir: "./output"
  work_hours: [9, 18]
""")
    config = Config(tmp_path)
    return CalendarRender(config)


def _make_event(dt, title, category="会议", time="10:00-11:00", participants=None):
    return Event(
        id="evt_test_001", date=dt, time=time, title=title,
        category=category, participants=participants or [],
        location="3楼会议室",
    )


class TestBuildEventData:
    """测试 _build_event_data 事件数据转换"""

    def test_basic_conversion(self, render):
        """基本事件转换"""
        events = [
            _make_event(date(2026, 3, 25), "进度会", time="14:00-15:30"),
        ]
        result = render._build_event_data(events)
        assert len(result) == 1

        item = result[0]
        assert item["id"] == "evt_test_001"
        assert item["category"] == "会议"
        assert item["title"] == "进度会"
        assert item["start_iso"] == "2026-03-25T14:00:00"
        assert item["end_iso"] == "2026-03-25T15:30:00"
        assert item["location"] == "3楼会议室"

    def test_no_end_time_defaults_1h(self, render):
        """没有结束时间默认 1 小时"""
        events = [_make_event(date(2026, 3, 25), "会议", time="14:00")]
        result = render._build_event_data(events)
        assert result[0]["start_iso"] == "2026-03-25T14:00:00"
        assert result[0]["end_iso"] == "2026-03-25T15:00:00"

    def test_participants(self, render):
        """参与人传递"""
        events = [_make_event(date(2026, 3, 25), "会议", participants=["张总", "李经理"])]
        result = render._build_event_data(events)
        assert result[0]["participants"] == ["张总", "李经理"]

    def test_multiple_events(self, render):
        """多个事件"""
        events = [
            _make_event(date(2026, 3, 25), "A", time="09:00-10:00"),
            _make_event(date(2026, 3, 25), "B", time="14:00-15:00"),
        ]
        result = render._build_event_data(events)
        assert len(result) == 2

    def test_empty_events(self, render):
        """空事件列表"""
        result = render._build_event_data([])
        assert result == []


class TestRenderHtml:
    """测试 render_html 输出"""

    def test_html_contains_title(self, render):
        """HTML 包含标题"""
        events = [_make_event(date(2026, 3, 25), "test_meeting")]
        html = render.render_html(events, title="Test Calendar")
        assert "Test Calendar" in html
        assert "test_meeting" in html

    def test_html_contains_events_js(self, render):
        """HTML 包含事件 JavaScript 数据"""
        events = [_make_event(date(2026, 3, 25), "进度会", time="14:00-15:30")]
        html = render.render_html(events)
        assert "2026-03-25T14:00:00" in html
        assert "2026-03-25T15:30:00" in html

    def test_html_view_type(self, render):
        """不同视图类型"""
        events = [_make_event(date(2026, 3, 25), "会议")]
        for view in ["week", "month", "day"]:
            html = render.render_html(events, view=view)
            assert f"defaultView: '{view}'" in html

    def test_html_dynamic_hours(self, render):
        """事件时间影响显示的小时范围"""
        events = [_make_event(date(2026, 3, 25), "早会", time="07:00-08:00")]
        html = render.render_html(events)
        # 07:00 的事件应使 hourStart 变为 7
        assert "hourStart: 7" in html

    def test_html_empty_events(self, render):
        """空事件仍生成有效 HTML"""
        html = render.render_html([])
        assert "<!DOCTYPE html>" in html
        assert "toastui-calendar" in html


class TestConfigWorkHours:
    """测试 Config.work_hours 属性"""

    def test_work_hours_from_config(self, render):
        """从配置读取工作时间"""
        work_start, work_end = render.config.work_hours
        assert work_start == 9
        assert work_end == 18
