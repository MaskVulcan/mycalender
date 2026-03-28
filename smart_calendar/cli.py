"""CLI 入口 — sc 命令"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from smart_calendar.utils.config import Config
from smart_calendar.storage.event_store import Event, EventStore
from smart_calendar.storage.people_store import Person, PeopleStore
from smart_calendar.parser.date_parser import DateParser
from smart_calendar.query.engine import QueryEngine
from smart_calendar.query.aggregator import Aggregator
from smart_calendar.render.text_render import TextRender


# ─── 自定义异常 ──────────────────────────────────────────────


class CalendarError(Exception):
    """Smart Calendar 业务异常（用户输入错误等）"""


# ─── 服务容器（按需构建） ──────────────────────────────────────


class _Services:
    """按需构建服务实例，避免每次 CLI 调用都初始化全部组件"""

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent
        self._base_dir = base_dir
        self._config: Config | None = None
        self._store: EventStore | None = None
        self._people: PeopleStore | None = None
        self._parser: DateParser | None = None
        self._query: QueryEngine | None = None
        self._aggregator: Aggregator | None = None
        self._render: TextRender | None = None

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = Config(self._base_dir)
        return self._config

    @property
    def store(self) -> EventStore:
        if self._store is None:
            self._store = EventStore(self.config.events_dir)
        return self._store

    @property
    def people(self) -> PeopleStore:
        if self._people is None:
            self._people = PeopleStore(self.config.people_dir)
        return self._people

    @property
    def parser(self) -> DateParser:
        if self._parser is None:
            self._parser = DateParser(self.config.timezone)
        return self._parser

    @property
    def query(self) -> QueryEngine:
        if self._query is None:
            self._query = QueryEngine(self.store)
        return self._query

    @property
    def aggregator(self) -> Aggregator:
        if self._aggregator is None:
            self._aggregator = Aggregator(self.config.timezone)
        return self._aggregator

    @property
    def render(self) -> TextRender:
        if self._render is None:
            self._render = TextRender(self.config)
        return self._render


def _svc() -> _Services:
    """获取服务容器实例"""
    return _Services()


# ─── add 命令 ───────────────────────────────────────────────


def cmd_add(args):
    """添加日程"""
    svc = _svc()

    text = " ".join(args.text)

    # 解析日期
    dt = svc.parser.parse(text)
    if dt is None and args.date:
        dt = svc.parser.parse(args.date)
    if dt is None:
        raise CalendarError("无法识别日期，请用 --date 指定，如 --date '明天' 或 --date '2026-03-25'")

    event_date = dt.date() if hasattr(dt, "date") and callable(dt.date) else dt

    # 解析时间
    time_str = args.time or svc.parser.parse_time_only(text)
    if not time_str:
        time_str = f"{dt.hour:02d}:{dt.minute:02d}" if dt.hour or dt.minute else "09:00"

    # 提取标题：去掉日期时间相关词后的核心内容
    title = args.title or _extract_title(text)

    # 参与人
    participants = []
    if args.with_people:
        participants = [p.strip() for p in args.with_people.split(",")]

    # 类别
    category = args.category or "其他"

    event = Event(
        id="",
        date=event_date,
        time=time_str,
        title=title,
        category=category,
        participants=participants,
        location=args.location or "",
        notes=args.notes or "",
        priority=args.priority or "normal",
    )

    # 冲突检测
    conflicts = svc.store.find_conflicts(event_date, time_str)
    if conflicts:
        print(f"\n⚠️  时间冲突提醒 — {svc.parser.format_date(event_date)} {time_str}:")
        for c in conflicts:
            print(f"   • {c.time} {c.title}")
        print("   （日程仍已添加，请注意安排）")

    event = svc.store.add(event)

    # 展示确认
    icon = svc.config.get_category_icon(category)
    print(f"\n✅ 日程已添加:")
    print(f"   {icon} {event.title}")
    print(f"   📆 {svc.parser.format_date(event.date)} {event.time}")
    if participants:
        print(f"   👥 {', '.join(participants)}")
    if event.notes:
        print(f"   📝 {event.notes}")
    print(f"   🔖 ID: {event.id}\n")


# 预编译标题提取正则（模块级缓存，避免每次调用重复编译）
_TITLE_PATTERNS = [re.compile(p) for p in [
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?",  # 2026-03-25
    r"\d{1,2}[月./]\d{1,2}[号日]?",               # 3月28号
    r"(?:这|本|下|上)周[一二三四五六日天]",           # 下周三
    r"(?:这|本|下|上)(?:周|个?月)",                  # 下周/这个月
    r"(?:今天|明天|后天|大后天)",                     # 明天
    r"(?:上午|下午|晚上|早上|中午)",                  # 下午
    r"\d{1,2}[点时:：]\d{0,2}[分半]?",              # 3点/3点半/14:00
    r"^和(?=\S)",                                   # 句首 "和" 后紧跟人名
]]
_TITLE_CLEANUP_RE = re.compile(r"^[和与\s，,。.、]+")


def _extract_title(text: str) -> str:
    """从自然语言中提取事件标题（去掉日期时间词）"""
    result = text
    for p in _TITLE_PATTERNS:
        result = p.sub("", result)
    # 清理残余的连接词和标点（仅清理 "和"、"与"，不清理 "跟"）
    result = _TITLE_CLEANUP_RE.sub("", result)
    result = result.strip().strip("，,。. ")
    return result if result else text


# ─── show 命令 ───────────────────────────────────────────────


def cmd_show(args):
    """查询并展示日程"""
    svc = _svc()

    # 确定查询范围
    if args.range:
        result = svc.parser.parse_range(args.range)
        if result:
            start, end = result
        else:
            raise CalendarError(f"无法识别范围: {args.range}")
    elif args.month:
        import pendulum

        now = pendulum.now(svc.config.timezone)
        start = now.start_of("month").date()
        end = now.end_of("month").date()
    elif args.week:
        import pendulum

        now = pendulum.now(svc.config.timezone)
        start = now.start_of("week").date()
        end = now.end_of("week").date()
    elif args.date:
        dt = svc.parser.parse_date_only(args.date)
        if dt:
            start = end = dt
        else:
            raise CalendarError(f"无法识别日期: {args.date}")
    else:
        # 默认：未来 7 天
        start = date.today()
        end = start + timedelta(days=6)

    # 查询
    if args.category:
        events = svc.query.by_category(args.category, start, end)
        title_suffix = f"[{args.category}]"
    elif args.with_people:
        events = svc.query.by_participant(args.with_people, start, end)
        title_suffix = f"[与{args.with_people}]"
    elif args.search:
        events = svc.query.search(args.search, start, end)
        title_suffix = f"[搜索: {args.search}]"
    else:
        events = svc.query.by_range(start, end)
        title_suffix = ""

    # 构建标题
    date_label = svc.parser.format_date(start)
    if start == end:
        title = f"📅 {date_label} {title_suffix}"
    else:
        end_label = svc.parser.format_date(end)
        title = f"📅 {date_label} ~ {end_label} {title_suffix}"

    svc.render.render_schedule(events, title=title.strip())

    # 展示日程中涉及的已知人物的协作提示
    all_participants = set()
    for e in events:
        for p in e.participants:
            all_participants.add(p)
    if all_participants:
        tips_shown = False
        for name in sorted(all_participants):
            person = svc.people.get(name)
            if person and (person.collaboration_tips or person.personality):
                if not tips_shown:
                    print("\n💡 协作备忘:")
                    tips_shown = True
                parts = []
                if person.personality:
                    parts.append(f"性格: {'; '.join(person.personality[:2])}")
                if person.collaboration_tips:
                    parts.append(f"建议: {'; '.join(person.collaboration_tips[:2])}")
                print(f"   👤 {name} — {' | '.join(parts)}")
        if tips_shown:
            print()


# ─── stats 命令 ───────────────────────────────────────────────


def cmd_stats(args):
    """类别聚合统计"""
    svc = _svc()

    period = "week" if args.week else "month"

    # 获取时间范围内的所有事件
    start, end, _ = svc.aggregator.get_period_range(period)
    all_events = svc.store.get_range(start, end)

    if args.all:
        # 所有类别对比
        categories = list({e.category for e in all_events})
        if not categories:
            print("📊 该时段暂无日程数据")
            return
        results = svc.aggregator.compare(all_events, categories, period)
        svc.render.render_compare(results)
    else:
        category = args.category or "其他"
        result = svc.aggregator.summary(all_events, category, period)
        svc.render.render_stats(result)


# ─── edit 命令 ───────────────────────────────────────────────


def cmd_edit(args):
    """编辑日程"""
    svc = _svc()

    kwargs = {}
    if args.title:
        kwargs["title"] = args.title
    if args.time:
        kwargs["time"] = args.time
    if args.category:
        kwargs["category"] = args.category
    if args.with_people is not None:
        kwargs["participants"] = [p.strip() for p in args.with_people.split(",")]
    if args.location is not None:
        kwargs["location"] = args.location
    if args.notes is not None:
        kwargs["notes"] = args.notes
    if args.priority:
        kwargs["priority"] = args.priority

    if not kwargs:
        raise CalendarError("请至少指定一个要修改的字段，如 --title, --time, --category 等")

    updated = svc.store.update(args.event_id, **kwargs)
    if updated:
        icon = svc.config.get_category_icon(updated.category)
        print(f"\n✅ 日程已更新:")
        print(f"   {icon} {updated.title}")
        print(f"   📆 {svc.parser.format_date(updated.date)} {updated.time}")
        if updated.participants:
            print(f"   👥 {', '.join(updated.participants)}")
        print(f"   🔖 ID: {updated.id}\n")
    else:
        raise CalendarError(f"未找到: {args.event_id}")


# ─── delete 命令 ──────────────────────────────────────────────


def cmd_delete(args):
    """删除日程"""
    svc = _svc()
    if svc.store.delete(args.event_id):
        print(f"✅ 已删除: {args.event_id}")
    else:
        print(f"❌ 未找到: {args.event_id}")


# ─── render 命令 ──────────────────────────────────────────────


def cmd_render(args):
    """生成日历图片"""
    svc = _svc()

    import pendulum

    now = pendulum.now(svc.config.timezone)

    # 确定时间范围
    if args.range:
        result = svc.parser.parse_range(args.range)
        if result:
            start, end = result
        else:
            raise CalendarError(f"无法识别范围: {args.range}")
    elif args.month:
        start = now.start_of("month").date()
        end = now.end_of("month").date()
    else:
        # 默认本周
        start = now.start_of("week").date()
        end = now.end_of("week").date()

    # 输出路径
    output_dir = svc.config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    out = None  # 防止提前 return 时 out 未定义

    if args.heatmap:
        # ── 热力图模式 ──
        from smart_calendar.render.heatmap_render import HeatmapRender

        heatmap = HeatmapRender(svc.config)
        category = args.heatmap

        all_events = svc.store.get_range(start, end)

        if category == "__all__":
            # 所有类别对比热力图
            categories = list({e.category for e in all_events})
            if not categories:
                print("📊 该时段暂无日程数据")
                return
            period = "month" if args.month else "week"
            results = svc.aggregator.compare(all_events, categories, period)
            out = output_dir / "heatmap_compare.png"
            heatmap.render_category_comparison(results, out)
            print(f"✅ 类别对比热力图已生成: {out}")
            # 同时输出文字统计（复用已有 results）
            svc.render.render_compare(results)
        elif args.year:
            # 全年热力图
            from collections import Counter

            year_start = pendulum.date(now.year, 1, 1)
            year_end = pendulum.date(now.year, 12, 31)
            year_events = svc.store.get_range(year_start, year_end)
            filtered = [e for e in year_events if e.category == category]
            daily = dict(Counter(e.date for e in filtered))
            icon = svc.config.get_category_icon(category)
            cmap = svc.config.get_category_cmap(category)
            out = output_dir / f"heatmap_{category}_year.png"
            heatmap.render_year(daily, out, year=now.year, title=f"{icon} {now.year}年「{category}」", cmap=cmap)
            print(f"✅ 年度热力图已生成: {out}")
        else:
            # 单月/单周热力图
            period = "month" if args.month else "week"
            result = svc.aggregator.summary(all_events, category, period)
            out = output_dir / f"heatmap_{category}_{period}.png"
            heatmap.render_month(result, out)
            print(f"✅ 热力图已生成: {out}")
            # 同时输出文字统计（复用已有 result）
            svc.render.render_stats(result)

    else:
        # ── 日历图模式（TOAST UI）──
        from smart_calendar.render.calendar_render import CalendarRender

        cal_render = CalendarRender(svc.config)

        view = args.view or "week"
        events = svc.store.get_range(start, end)

        # focus_date: 视图中心日期
        if view == "month":
            focus = start.replace(day=15)
        elif view == "day" and args.date:
            focus = svc.parser.parse_date_only(args.date) or start
        else:
            focus = start

        date_range_str = f"{svc.parser.format_date(start)} ~ {svc.parser.format_date(end)}"
        out = output_dir / f"calendar_{view}.png"

        print(f"🎨 正在生成 {view} 视图日历图...")
        cal_render.render_png(
            events,
            output_path=out,
            view=view,
            focus_date=focus,
            title="Smart Calendar",
            date_range=date_range_str,
        )
        print(f"✅ 日历图已生成: {out}")

        # 同时输出文字版
        svc.render.render_schedule(events, title=f"📅 {date_range_str}")

    # 尝试用系统默认应用打开图片（跨平台）
    if args.open and out and out.exists():
        import subprocess

        if sys.platform == "darwin":
            subprocess.run(["open", str(out)], check=False)
        elif sys.platform == "linux":
            subprocess.run(["xdg-open", str(out)], check=False)
        elif sys.platform == "win32":
            import os
            os.startfile(str(out))


# ─── people 子命令 ───────────────────────────────────────────


def _require_name(args) -> str:
    """校验并返回人物姓名"""
    if not args.name:
        raise CalendarError("请指定姓名")
    return args.name


def _cmd_people_add(args, svc: _Services):
    """people add: 创建人物档案"""
    name = _require_name(args)

    person = svc.people.get(name)
    if person:
        print(f"⚠️  「{name}」已存在，使用 'sc people show {name}' 查看")
        return

    person = Person(
        name=name,
        role=args.role or "",
        contact=args.contact or "",
        tags=[t.strip() for t in args.tags.split(",")] if args.tags else [],
    )

    if args.personality:
        person.personality = [p.strip() for p in args.personality.split(",")]
    if args.tips:
        person.collaboration_tips = [t.strip() for t in args.tips.split(",")]

    svc.people.add(person)
    print(f"\n✅ 人物档案已创建: {name}")
    svc.render.render_person(person)


def _cmd_people_show(args, svc: _Services):
    """people show: 查看人物档案"""
    name = _require_name(args)

    person = svc.people.get(name)
    if not person:
        raise CalendarError(f"未找到「{name}」的档案")
    svc.render.render_person(person)

    # 同时展示与此人相关的近期日程
    start = date.today() - timedelta(days=30)
    end = date.today() + timedelta(days=30)
    events = svc.query.by_participant(name, start, end)
    if events:
        svc.render.render_schedule(events, title=f"📅 与「{name}」相关的近期日程")


def _cmd_people_note(args, svc: _Services):
    """people note: 追加备注"""
    name = _require_name(args)

    note_text = " ".join(args.note_text) if args.note_text else ""
    if not note_text:
        raise CalendarError("请提供备注内容，如 sc people note 张总 喜欢早上开会")

    if args.as_personality:
        person = svc.people.add_personality(name, note_text)
        label = "性格特征"
    elif args.as_tip:
        person = svc.people.add_tip(name, note_text)
        label = "协作建议"
    else:
        person = svc.people.add_note(name, note_text)
        label = "备忘"

    if person:
        print(f"✅ 已为「{name}」添加{label}: {note_text}")
    else:
        raise CalendarError(f"未找到「{name}」的档案，请先用 'sc people add {name}' 创建")


def _cmd_people_list(args, svc: _Services):
    """people list: 列出/搜索人物"""
    keyword = args.name
    if keyword:
        persons = svc.people.search(keyword)
        if not persons:
            print(f"🔍 未找到匹配「{keyword}」的人物")
            return
    else:
        persons = svc.people.list_all()
    svc.render.render_people_list(persons)


def _cmd_people_update(args, svc: _Services):
    """people update: 更新人物字段"""
    name = _require_name(args)

    kwargs = {}
    if args.role:
        kwargs["role"] = args.role
    if args.contact:
        kwargs["contact"] = args.contact
    if args.tags:
        kwargs["tags"] = [t.strip() for t in args.tags.split(",")]
    if not kwargs:
        raise CalendarError("请指定要更新的字段，如 --role, --contact, --tags")

    person = svc.people.update(name, **kwargs)
    if person:
        print(f"✅ 已更新「{name}」的档案")
        svc.render.render_person(person)
    else:
        raise CalendarError(f"未找到「{name}」的档案")


def _cmd_people_delete(args, svc: _Services):
    """people delete: 删除人物档案"""
    name = _require_name(args)

    if svc.people.delete(name):
        print(f"✅ 已删除「{name}」的档案")
    else:
        raise CalendarError(f"未找到「{name}」的档案")


_PEOPLE_ACTIONS = {
    "add": _cmd_people_add,
    "show": _cmd_people_show,
    "note": _cmd_people_note,
    "list": _cmd_people_list,
    "update": _cmd_people_update,
    "delete": _cmd_people_delete,
}


def cmd_people(args):
    """人物档案管理"""
    svc = _svc()
    handler = _PEOPLE_ACTIONS.get(args.action)
    if handler:
        handler(args, svc)
    else:
        raise CalendarError("未知操作，可用: add, show, note, list, update, delete")


# ─── 主入口 ──────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="sc",
        description="Smart Calendar — 基于 Markdown 的个人日程管理工具",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # ── add ──
    p_add = subparsers.add_parser("add", help="添加日程")
    p_add.add_argument("text", nargs="*", help="自然语言描述，如 '明天下午3点和张总开会'")
    p_add.add_argument("--date", "-d", help="指定日期")
    p_add.add_argument("--time", "-t", help="指定时间，如 14:00 或 14:00-15:30")
    p_add.add_argument("--title", help="事件标题（不指定则从 text 中提取）")
    p_add.add_argument("--category", "-c", help="事件类别", default="其他")
    p_add.add_argument("--with", dest="with_people", help="参与人，逗号分隔")
    p_add.add_argument("--location", "-l", help="地点")
    p_add.add_argument("--notes", "-n", help="备注")
    p_add.add_argument("--priority", "-p", choices=["high", "normal", "low"], default="normal")
    p_add.set_defaults(func=cmd_add)

    # ── show ──
    p_show = subparsers.add_parser("show", help="查询日程")
    p_show.add_argument("--date", "-d", help="指定日期")
    p_show.add_argument("--week", "-w", action="store_true", help="本周")
    p_show.add_argument("--month", "-m", action="store_true", help="本月")
    p_show.add_argument("--range", "-r", help="日期范围，如 '3.20-3.31' 或 '这周'")
    p_show.add_argument("--category", "-c", help="按类别筛选")
    p_show.add_argument("--with", dest="with_people", help="按参与人筛选")
    p_show.add_argument("--search", "-s", help="关键字搜索")
    p_show.set_defaults(func=cmd_show)

    # ── stats ──
    p_stats = subparsers.add_parser("stats", help="类别统计")
    p_stats.add_argument("category", nargs="?", help="要统计的类别")
    p_stats.add_argument("--week", "-w", action="store_true", help="统计本周")
    p_stats.add_argument("--all", "-a", action="store_true", help="所有类别对比")
    p_stats.set_defaults(func=cmd_stats)

    # ── render ──
    p_render = subparsers.add_parser("render", help="生成日历图片")
    p_render.add_argument("--view", "-v", choices=["month", "week", "day"], help="日历视图 (TOAST UI)")
    p_render.add_argument("--heatmap", help="热力图模式：指定类别名，或 __all__ 对比全部")
    p_render.add_argument("--week", "-w", action="store_true", help="本周范围")
    p_render.add_argument("--month", "-m", action="store_true", help="本月范围")
    p_render.add_argument("--year", "-y", action="store_true", help="全年热力图")
    p_render.add_argument("--range", "-r", help="日期范围")
    p_render.add_argument("--date", "-d", help="指定日期（day 视图用）")
    p_render.add_argument("--open", "-o", action="store_true", help="生成后自动打开图片")
    p_render.set_defaults(func=cmd_render)

    # ── people ──
    p_people = subparsers.add_parser("people", help="人物档案管理")
    p_people.add_argument("action", choices=["add", "show", "note", "list", "update", "delete"],
                          help="操作: add/show/note/list/update/delete")
    p_people.add_argument("name", nargs="?", help="人物姓名")
    p_people.add_argument("note_text", nargs="*", help="备注内容（note 操作时使用）")
    p_people.add_argument("--role", help="角色/职位")
    p_people.add_argument("--contact", help="联系方式")
    p_people.add_argument("--tags", help="标签，逗号分隔")
    p_people.add_argument("--personality", help="性格特征，逗号分隔（add 时使用）")
    p_people.add_argument("--tips", help="协作建议，逗号分隔（add 时使用）")
    p_people.add_argument("--as-personality", action="store_true", help="note 操作: 标记内容为性格特征")
    p_people.add_argument("--as-tip", action="store_true", help="note 操作: 标记内容为协作建议")
    p_people.set_defaults(func=cmd_people)

    # ── edit ──
    p_edit = subparsers.add_parser("edit", help="编辑日程")
    p_edit.add_argument("event_id", help="事件 ID")
    p_edit.add_argument("--title", help="新标题")
    p_edit.add_argument("--time", "-t", help="新时间")
    p_edit.add_argument("--category", "-c", help="新类别")
    p_edit.add_argument("--with", dest="with_people", help="新参与人，逗号分隔")
    p_edit.add_argument("--location", "-l", help="新地点")
    p_edit.add_argument("--notes", "-n", help="新备注")
    p_edit.add_argument("--priority", "-p", choices=["high", "normal", "low"], help="新优先级")
    p_edit.set_defaults(func=cmd_edit)

    # ── delete ──
    p_del = subparsers.add_parser("delete", help="删除日程")
    p_del.add_argument("event_id", help="事件 ID")
    p_del.set_defaults(func=cmd_delete)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        args.func(args)
    except CalendarError as e:
        print(f"❌ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
