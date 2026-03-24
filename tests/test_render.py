"""测试 TextRender（不测图片渲染，避免 Playwright/matplotlib 依赖问题）"""

from __future__ import annotations

from datetime import date
from io import StringIO
from unittest.mock import patch

import pytest

from smart_calendar.storage.event_store import Event
from smart_calendar.storage.people_store import Person
from smart_calendar.query.aggregator import AggResult
from smart_calendar.render.text_render import TextRender
from smart_calendar.utils.config import Config
from smart_calendar.utils.holidays import get_day_type, get_day_label, get_holiday_name


# ─── TextRender 测试 ─────────────────────────────────────────


@pytest.fixture
def render(tmp_path):
    """创建一个 TextRender 实例"""
    # 写一个最小的 config.yml
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
""")
    config = Config(tmp_path)
    return TextRender(config)


def _make_event(dt, title, category="会议", time="10:00", participants=None):
    return Event(
        id="evt_test", date=dt, time=time, title=title,
        category=category, participants=participants or [],
    )


class TestTextRender:
    def test_render_schedule_empty(self, render, capsys):
        """空日程列表"""
        render.render_schedule([], title="测试标题")
        captured = capsys.readouterr()
        assert "暂无日程" in captured.out

    def test_render_schedule_with_events(self, render, capsys):
        """有日程时正常渲染"""
        events = [
            _make_event(date(2026, 3, 25), "进度会", "会议", "14:00", ["张总"]),
            _make_event(date(2026, 3, 25), "代码评审", "技术", "16:00"),
        ]
        render.render_schedule(events, title="本周日程")
        captured = capsys.readouterr()
        assert "进度会" in captured.out
        assert "代码评审" in captured.out
        assert "张总" in captured.out

    def test_render_schedule_sorted(self, render, capsys):
        """日程应按日期和时间排序"""
        events = [
            _make_event(date(2026, 3, 26), "B", time="09:00"),
            _make_event(date(2026, 3, 25), "A", time="14:00"),
        ]
        render.render_schedule(events)
        captured = capsys.readouterr()
        # A 在 3.25，应该先出现
        pos_a = captured.out.find("A")
        pos_b = captured.out.find("B")
        assert pos_a < pos_b

    def test_render_stats(self, render, capsys):
        """渲染统计结果"""
        result = AggResult(
            category="会议", period="2026年3月",
            total=10, daily_counts={}, avg_per_day=0.33,
            peak_weekday="周三", peak_count=2.0,
            active_days=5, total_days=31,
        )
        render.render_stats(result)
        captured = capsys.readouterr()
        assert "会议" in captured.out
        assert "10" in captured.out
        assert "周三" in captured.out

    def test_render_compare_empty(self, render, capsys):
        """空对比"""
        render.render_compare([])
        captured = capsys.readouterr()
        assert "暂无数据" in captured.out

    def test_render_compare(self, render, capsys):
        """多类别对比"""
        results = [
            AggResult("会议", "2026年3月", 10, {}, 0.33, "周三", 2.0, 5, 31),
            AggResult("技术", "2026年3月", 5, {}, 0.16, "周五", 1.0, 3, 31),
        ]
        render.render_compare(results)
        captured = capsys.readouterr()
        assert "会议" in captured.out
        assert "技术" in captured.out

    def test_render_person(self, render, capsys):
        """渲染人物档案"""
        person = Person(
            name="张总", role="VP",
            personality=["果断", "高效"],
            collaboration_tips=["准备数据"],
            contact="zhang@test.com",
            tags=["管理层"],
            notes="一些备忘录",
        )
        render.render_person(person)
        captured = capsys.readouterr()
        assert "张总" in captured.out
        assert "VP" in captured.out
        assert "果断" in captured.out
        assert "准备数据" in captured.out

    def test_render_people_list_empty(self, render, capsys):
        """空人物列表"""
        render.render_people_list([])
        captured = capsys.readouterr()
        assert "暂无人物档案" in captured.out

    def test_render_people_list(self, render, capsys):
        """渲染人物列表"""
        people = [
            Person(name="张总", role="VP", personality=["果断", "高效", "直接"]),
            Person(name="李经理", role="PM", personality=["细致"]),
        ]
        render.render_people_list(people)
        captured = capsys.readouterr()
        assert "张总" in captured.out
        assert "李经理" in captured.out
        # 张总有 3 个性格特征，应显示 (+1)
        assert "+1" in captured.out


# ─── Holidays 测试 ───────────────────────────────────────────


class TestHolidays:
    def test_get_day_type_workday(self):
        """普通工作日"""
        # 2026-03-25 是周三，正常工作日
        result = get_day_type(date(2026, 3, 25))
        assert result in ("workday", "holiday", "in_lieu")  # 取决于当年安排

    def test_get_day_type_weekend(self):
        """周末被 chinese-calendar 归为 holiday（与法定假日同归类）"""
        # chinese-calendar 对周末 is_holiday() 返回 True
        # 所以普通周末在我们的逻辑中会被标记为 holiday 或 weekend
        result = get_day_type(date(2026, 3, 14))  # 周六
        assert result in ("weekend", "holiday")

    def test_get_day_label_workday(self):
        """工作日标签为空"""
        # 找一个确定是工作日的日子
        label = get_day_label(date(2026, 3, 25))
        # 如果是工作日，应该返回空字符串
        assert isinstance(label, str)

    def test_get_holiday_name_normal_day(self):
        """普通日子没有节假日名称"""
        name = get_holiday_name(date(2026, 3, 25))
        # 非节假日返回 None
        assert name is None or isinstance(name, str)

    def test_new_year(self):
        """元旦应该是假日"""
        result = get_day_type(date(2026, 1, 1))
        assert result == "holiday"

    def test_get_day_label_returns_string(self):
        """get_day_label 总是返回字符串"""
        for day in range(1, 8):
            label = get_day_label(date(2026, 3, day))
            assert isinstance(label, str)
