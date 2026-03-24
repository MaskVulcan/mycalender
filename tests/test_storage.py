"""测试 EventStore 和 PeopleStore"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from smart_calendar.storage.event_store import Event, EventStore
from smart_calendar.storage.people_store import Person, PeopleStore


# ─── fixtures ────────────────────────────────────────────────


@pytest.fixture
def tmp_events(tmp_path):
    """返回一个临时目录的 EventStore"""
    return EventStore(tmp_path / "events")


@pytest.fixture
def tmp_people(tmp_path):
    """返回一个临时目录的 PeopleStore"""
    return PeopleStore(tmp_path / "people")


# ─── EventStore 测试 ─────────────────────────────────────────


class TestEventStore:
    def test_add_and_get(self, tmp_events):
        """添加一条日程后能查到"""
        event = Event(
            id="", date=date(2026, 3, 25), time="14:00",
            title="测试会议", category="会议",
        )
        saved = tmp_events.add(event)

        assert saved.id.startswith("evt_20260325_")
        assert saved.title == "测试会议"

        # 按日期查回来
        results = tmp_events.get(date(2026, 3, 25))
        assert len(results) == 1
        assert results[0].title == "测试会议"
        assert results[0].id == saved.id

    def test_add_multiple_same_day(self, tmp_events):
        """同一天添加多条日程"""
        dt = date(2026, 3, 25)
        tmp_events.add(Event(id="", date=dt, time="09:00", title="晨会"))
        tmp_events.add(Event(id="", date=dt, time="14:00", title="午会"))
        tmp_events.add(Event(id="", date=dt, time="10:00", title="评审"))

        results = tmp_events.get(dt)
        assert len(results) == 3
        # 应按时间排序
        assert results[0].title == "晨会"
        assert results[1].title == "评审"
        assert results[2].title == "午会"

    def test_get_range(self, tmp_events):
        """跨天范围查询"""
        tmp_events.add(Event(id="", date=date(2026, 3, 25), time="10:00", title="A"))
        tmp_events.add(Event(id="", date=date(2026, 3, 26), time="10:00", title="B"))
        tmp_events.add(Event(id="", date=date(2026, 3, 28), time="10:00", title="C"))

        results = tmp_events.get_range(date(2026, 3, 25), date(2026, 3, 27))
        assert len(results) == 2
        titles = {e.title for e in results}
        assert titles == {"A", "B"}

    def test_delete(self, tmp_events):
        """删除日程"""
        saved = tmp_events.add(
            Event(id="", date=date(2026, 3, 25), time="14:00", title="待删除")
        )
        assert tmp_events.delete(saved.id) is True
        assert tmp_events.get(date(2026, 3, 25)) == []

    def test_delete_nonexistent(self, tmp_events):
        """删除不存在的 ID"""
        assert tmp_events.delete("evt_20260101_000000") is False

    def test_update(self, tmp_events):
        """更新日程字段"""
        saved = tmp_events.add(
            Event(id="", date=date(2026, 3, 25), time="14:00", title="旧标题")
        )
        updated = tmp_events.update(saved.id, title="新标题")
        assert updated is not None
        assert updated.title == "新标题"

        # 重新读取确认持久化
        results = tmp_events.get(date(2026, 3, 25))
        assert results[0].title == "新标题"

    def test_get_empty_day(self, tmp_events):
        """查询没有日程的日期"""
        assert tmp_events.get(date(2099, 1, 1)) == []

    def test_event_properties(self):
        """Event 的 start_hour/start_minute 属性"""
        e = Event(id="x", date=date(2026, 1, 1), time="14:30-15:00", title="t")
        assert e.start_hour == 14
        assert e.start_minute == 30

    def test_event_to_dict_and_back(self):
        """序列化/反序列化"""
        e = Event(
            id="evt_001", date=date(2026, 3, 25), time="14:00",
            title="测试", category="技术", participants=["张三"],
            location="3楼", notes="备注", priority="high",
        )
        d = e.to_dict()
        assert d["date"] == "2026-03-25"
        assert d["participants"] == ["张三"]

        restored = Event.from_dict(d)
        assert restored.id == e.id
        assert restored.date == e.date
        assert restored.participants == ["张三"]


# ─── PeopleStore 测试 ────────────────────────────────────────


class TestPeopleStore:
    def test_add_and_get(self, tmp_people):
        """创建并读取人物档案"""
        person = Person(
            name="张总", role="VP",
            personality=["果断", "高效"],
            collaboration_tips=["准备数据"],
            contact="zhang@test.com",
            tags=["管理层"],
        )
        tmp_people.add(person)

        loaded = tmp_people.get("张总")
        assert loaded is not None
        assert loaded.name == "张总"
        assert loaded.role == "VP"
        assert loaded.personality == ["果断", "高效"]
        assert loaded.tags == ["管理层"]

    def test_get_nonexistent(self, tmp_people):
        """查询不存在的人物"""
        assert tmp_people.get("不存在") is None

    def test_update(self, tmp_people):
        """更新人物字段"""
        tmp_people.add(Person(name="李四", role="工程师"))
        updated = tmp_people.update("李四", role="高级工程师", contact="li@test.com")
        assert updated is not None
        assert updated.role == "高级工程师"
        assert updated.contact == "li@test.com"

    def test_add_personality(self, tmp_people):
        """追加性格特征"""
        tmp_people.add(Person(name="王五", personality=["细心"]))
        person = tmp_people.add_personality("王五", "善良")
        assert person is not None
        assert "善良" in person.personality
        assert len(person.personality) == 2

    def test_add_personality_no_duplicate(self, tmp_people):
        """重复的性格特征不会添加"""
        tmp_people.add(Person(name="赵六", personality=["细心"]))
        tmp_people.add_personality("赵六", "细心")
        person = tmp_people.get("赵六")
        assert person.personality == ["细心"]

    def test_add_tip(self, tmp_people):
        """追加协作建议"""
        tmp_people.add(Person(name="孙七"))
        person = tmp_people.add_tip("孙七", "邮件确认")
        assert "邮件确认" in person.collaboration_tips

    def test_add_note(self, tmp_people):
        """追加自由笔记"""
        tmp_people.add(Person(name="周八", notes="初始笔记"))
        person = tmp_people.add_note("周八", "补充内容")
        assert "初始笔记" in person.notes
        assert "补充内容" in person.notes

    def test_list_all(self, tmp_people):
        """列出所有人物"""
        tmp_people.add(Person(name="A"))
        tmp_people.add(Person(name="B"))
        tmp_people.add(Person(name="C"))

        result = tmp_people.list_all()
        names = {p.name for p in result}
        assert names == {"A", "B", "C"}

    def test_search(self, tmp_people):
        """搜索人物"""
        tmp_people.add(Person(name="张总", role="VP", tags=["管理"]))
        tmp_people.add(Person(name="李经理", role="PM", tags=["项目"]))
        tmp_people.add(Person(name="王工程师", tags=["技术"]))

        # 按姓名搜
        assert len(tmp_people.search("张")) == 1
        # 按角色搜
        assert len(tmp_people.search("PM")) == 1
        # 按标签搜
        assert len(tmp_people.search("技术")) == 1
        # 无匹配
        assert len(tmp_people.search("不存在")) == 0

    def test_delete(self, tmp_people):
        """删除人物档案"""
        tmp_people.add(Person(name="临时"))
        assert tmp_people.delete("临时") is True
        assert tmp_people.get("临时") is None
        assert tmp_people.delete("临时") is False
