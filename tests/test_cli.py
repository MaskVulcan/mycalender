"""CLI 集成测试 — 测试 cmd_* 函数的主要逻辑路径"""

from __future__ import annotations

import argparse
import shutil
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from smart_calendar.cli import (
    CalendarError,
    _Services,
    _extract_title,
    cmd_add,
    cmd_show,
    cmd_delete,
    cmd_edit,
    cmd_stats,
    cmd_people,
)
from smart_calendar.storage.event_store import Event


# ─── helpers ────────────────────────────────────────────────


def _make_svc(tmp_path):
    """创建指向临时目录的 _Services"""
    # 创建 data/config.yml
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "events").mkdir()
    (data_dir / "people").mkdir()
    config_yml = data_dir / "config.yml"
    config_yml.write_text("""
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
    return _Services(tmp_path)


def _make_args(**kwargs):
    """构造模拟的 argparse.Namespace"""
    defaults = {
        "text": [],
        "date": None,
        "time": None,
        "title": None,
        "category": None,
        "with_people": None,
        "location": None,
        "notes": None,
        "priority": None,
        "week": False,
        "month": False,
        "range": None,
        "search": None,
        "all": False,
        "event_id": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.fixture
def svc(tmp_path):
    return _make_svc(tmp_path)


# ─── _extract_title 测试 ──────────────────────────────────────


class TestExtractTitle:
    def test_remove_date_words(self):
        """去掉日期词"""
        result = _extract_title("明天下午3点和张总开会讨论Q1进度")
        assert "明天" not in result
        assert "下午" not in result
        assert "3点" not in result

    def test_keep_content(self):
        """保留核心内容"""
        result = _extract_title("明天下午3点开会讨论Q1进度")
        assert "讨论Q1进度" in result

    def test_empty_fallback(self):
        """全部是日期词时返回原文"""
        result = _extract_title("明天下午3点")
        assert len(result) > 0  # 不应返回空字符串

    def test_iso_date_removal(self):
        """去掉 ISO 格式日期"""
        result = _extract_title("2026-03-25代码评审")
        assert "2026" not in result
        assert "评审" in result


# ─── cmd_add 测试 ────────────────────────────────────────────


class TestCmdAdd:
    def test_add_with_explicit_args(self, svc, capsys):
        """用 --date --time 添加日程"""
        args = _make_args(
            text=["代码评审"],
            date="2026-03-25",
            time="14:00",
            title="代码评审",
            category="技术",
        )
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_add(args)

        captured = capsys.readouterr()
        assert "已添加" in captured.out
        assert "代码评审" in captured.out

        # 验证持久化
        events = svc.store.get(date(2026, 3, 25))
        assert len(events) == 1
        assert events[0].title == "代码评审"

    def test_add_with_natural_language(self, svc, capsys):
        """自然语言添加"""
        args = _make_args(
            text=["明天", "下午", "3点", "和", "张总", "开会"],
        )
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_add(args)

        captured = capsys.readouterr()
        assert "已添加" in captured.out

    def test_add_no_date_raises(self, svc):
        """无法识别日期时抛出 CalendarError"""
        args = _make_args(text=["一段无法解析日期的文本xyz"])
        with patch("smart_calendar.cli._svc", return_value=svc):
            with pytest.raises(CalendarError, match="无法识别日期"):
                cmd_add(args)

    def test_add_conflict_warning(self, svc, capsys):
        """添加冲突日程时给出警告"""
        dt = date(2026, 3, 25)
        svc.store.add(Event(
            id="", date=dt, time="14:00-15:00",
            title="已有会议", category="会议",
        ))
        args = _make_args(
            text=["评审"],
            date="2026-03-25",
            time="14:30",
            title="评审",
            category="技术",
        )
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_add(args)

        captured = capsys.readouterr()
        assert "冲突" in captured.out
        assert "已有会议" in captured.out


# ─── cmd_show 测试 ───────────────────────────────────────────


class TestCmdShow:
    def test_show_empty(self, svc, capsys):
        """空日程"""
        args = _make_args(date="2026-03-25")
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_show(args)

        captured = capsys.readouterr()
        assert "暂无日程" in captured.out

    def test_show_with_events(self, svc, capsys):
        """有日程时正常展示"""
        svc.store.add(Event(
            id="", date=date(2026, 3, 25), time="14:00",
            title="进度会", category="会议",
        ))
        args = _make_args(date="2026-03-25")
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_show(args)

        captured = capsys.readouterr()
        assert "进度会" in captured.out

    def test_show_by_category(self, svc, capsys):
        """按类别筛选"""
        dt = date(2026, 3, 25)
        svc.store.add(Event(id="", date=dt, time="10:00", title="会议A", category="会议"))
        svc.store.add(Event(id="", date=dt, time="14:00", title="学习B", category="学习"))
        args = _make_args(date="2026-03-25", category="会议")
        # show --category 需要 start/end 范围
        args.range = None
        args.week = False
        args.month = False
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_show(args)

        captured = capsys.readouterr()
        assert "会议A" in captured.out


# ─── cmd_edit 测试 ───────────────────────────────────────────


class TestCmdEdit:
    def test_edit_title(self, svc, capsys):
        """修改标题"""
        saved = svc.store.add(Event(
            id="", date=date(2026, 3, 25), time="14:00",
            title="旧标题", category="会议",
        ))
        args = _make_args(event_id=saved.id, title="新标题")
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_edit(args)

        captured = capsys.readouterr()
        assert "已更新" in captured.out
        assert "新标题" in captured.out

        # 验证持久化
        events = svc.store.get(date(2026, 3, 25))
        assert events[0].title == "新标题"

    def test_edit_no_field_raises(self, svc):
        """不指定任何字段时抛出异常"""
        saved = svc.store.add(Event(
            id="", date=date(2026, 3, 25), time="14:00",
            title="标题", category="会议",
        ))
        args = _make_args(event_id=saved.id)
        with patch("smart_calendar.cli._svc", return_value=svc):
            with pytest.raises(CalendarError, match="至少指定一个"):
                cmd_edit(args)

    def test_edit_nonexistent_raises(self, svc):
        """编辑不存在的 ID"""
        args = _make_args(event_id="evt_20260101_000000", title="新标题")
        with patch("smart_calendar.cli._svc", return_value=svc):
            with pytest.raises(CalendarError, match="未找到"):
                cmd_edit(args)


# ─── cmd_delete 测试 ─────────────────────────────────────────


class TestCmdDelete:
    def test_delete_existing(self, svc, capsys):
        """删除已有日程"""
        saved = svc.store.add(Event(
            id="", date=date(2026, 3, 25), time="14:00",
            title="待删", category="会议",
        ))
        args = _make_args(event_id=saved.id)
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_delete(args)

        captured = capsys.readouterr()
        assert "已删除" in captured.out

    def test_delete_nonexistent(self, svc, capsys):
        """删除不存在的 ID"""
        args = _make_args(event_id="evt_20260101_000000")
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_delete(args)

        captured = capsys.readouterr()
        assert "未找到" in captured.out


# ─── cmd_stats 测试 ──────────────────────────────────────────


class TestCmdStats:
    def test_stats_single_category(self, svc, capsys):
        """单类别统计"""
        svc.store.add(Event(
            id="", date=date.today(), time="10:00",
            title="会议A", category="会议",
        ))
        args = _make_args(category="会议", week=True, all=False)
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_stats(args)

        captured = capsys.readouterr()
        assert "会议" in captured.out

    def test_stats_all_categories(self, svc, capsys):
        """所有类别对比"""
        svc.store.add(Event(
            id="", date=date.today(), time="10:00",
            title="会议A", category="会议",
        ))
        svc.store.add(Event(
            id="", date=date.today(), time="14:00",
            title="学习B", category="技术",
        ))
        args = _make_args(all=True, week=True, category=None)
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_stats(args)

        captured = capsys.readouterr()
        assert "类别对比" in captured.out


# ─── cmd_people 测试 ─────────────────────────────────────────


class TestCmdPeople:
    def _people_args(self, **kwargs):
        defaults = {
            "action": "list",
            "name": None,
            "note_text": [],
            "role": None,
            "contact": None,
            "tags": None,
            "personality": None,
            "tips": None,
            "as_personality": False,
            "as_tip": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_people_add_and_show(self, svc, capsys):
        """添加并查看人物"""
        args = self._people_args(
            action="add", name="张总", role="VP",
            personality="果断,高效", tips="准备数据",
        )
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_people(args)

        captured = capsys.readouterr()
        assert "已创建" in captured.out

        # show
        args = self._people_args(action="show", name="张总")
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_people(args)

        captured = capsys.readouterr()
        assert "张总" in captured.out

    def test_people_list_empty(self, svc, capsys):
        """空人物列表"""
        args = self._people_args(action="list")
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_people(args)

        captured = capsys.readouterr()
        assert "暂无" in captured.out

    def test_people_delete(self, svc, capsys):
        """删除人物"""
        # 先添加
        from smart_calendar.storage.people_store import Person
        svc.people.add(Person(name="临时"))

        args = self._people_args(action="delete", name="临时")
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_people(args)

        captured = capsys.readouterr()
        assert "已删除" in captured.out

    def test_people_note(self, svc, capsys):
        """追加备注"""
        from smart_calendar.storage.people_store import Person
        svc.people.add(Person(name="测试人"))

        args = self._people_args(
            action="note", name="测试人",
            note_text=["这是一条备注"],
        )
        with patch("smart_calendar.cli._svc", return_value=svc):
            cmd_people(args)

        captured = capsys.readouterr()
        assert "已为" in captured.out
