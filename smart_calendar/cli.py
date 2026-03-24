"""CLI 入口 — sc 命令"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from smart_calendar.utils.config import Config
from smart_calendar.storage.event_store import Event, EventStore
from smart_calendar.parser.date_parser import DateParser
from smart_calendar.query.engine import QueryEngine
from smart_calendar.query.aggregator import Aggregator
from smart_calendar.render.text_render import TextRender


def _get_base_dir() -> Path:
    """获取项目根目录（mycalendar/）"""
    return Path(__file__).resolve().parent.parent


def _build_services(base_dir: Path | None = None):
    """构建所有服务实例"""
    if base_dir is None:
        base_dir = _get_base_dir()
    config = Config(base_dir)
    store = EventStore(config.events_dir)
    parser = DateParser(config.timezone)
    query = QueryEngine(store)
    aggregator = Aggregator(config.timezone)
    render = TextRender(config)
    return config, store, parser, query, aggregator, render


# ─── add 命令 ───────────────────────────────────────────────


def cmd_add(args):
    """添加日程"""
    config, store, parser, query, agg, render = _build_services()

    text = " ".join(args.text)

    # 解析日期
    dt = parser.parse(text)
    if dt is None and args.date:
        dt = parser.parse(args.date)
    if dt is None:
        print("❌ 无法识别日期，请用 --date 指定，如 --date '明天' 或 --date '2026-03-25'")
        sys.exit(1)

    event_date = dt.date() if hasattr(dt, "date") and callable(dt.date) else dt

    # 解析时间
    time_str = args.time or parser.parse_time_only(text)
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

    event = store.add(event)

    # 展示确认
    icon = config.get_category_icon(category)
    print(f"\n✅ 日程已添加:")
    print(f"   {icon} {event.title}")
    print(f"   📆 {parser.format_date(event.date)} {event.time}")
    if participants:
        print(f"   👥 {', '.join(participants)}")
    if event.notes:
        print(f"   📝 {event.notes}")
    print(f"   🔖 ID: {event.id}\n")


def _extract_title(text: str) -> str:
    """从自然语言中提取事件标题（去掉日期时间词）"""
    # 移除常见的日期时间表达（顺序很重要，长模式先匹配）
    patterns = [
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?",  # 2026-03-25
        r"\d{1,2}[月./]\d{1,2}[号日]?",               # 3月28号
        r"(?:这|本|下|上)周[一二三四五六日天]",           # 下周三
        r"(?:这|本|下|上)(?:周|个?月)",                  # 下周/这个月
        r"(?:今天|明天|后天|大后天)",                     # 明天
        r"(?:上午|下午|晚上|早上|中午)",                  # 下午
        r"\d{1,2}[点时:：]\d{0,2}[分半]?",              # 3点/3点半/14:00
        r"^[和跟]",                                     # 句首的"和"
    ]
    result = text
    for p in patterns:
        result = re.sub(p, "", result)
    # 清理残余的连接词和标点
    result = re.sub(r"^[和跟与\s，,。.、]+", "", result)
    result = result.strip().strip("，,。. ")
    return result if result else text


# ─── show 命令 ───────────────────────────────────────────────


def cmd_show(args):
    """查询并展示日程"""
    config, store, parser, query, agg, render = _build_services()

    # 确定查询范围
    if args.range:
        result = parser.parse_range(args.range)
        if result:
            start, end = result
        else:
            print(f"❌ 无法识别范围: {args.range}")
            sys.exit(1)
    elif args.month:
        import pendulum

        now = pendulum.now(config.timezone)
        start = now.start_of("month").date()
        end = now.end_of("month").date()
    elif args.week:
        import pendulum

        now = pendulum.now(config.timezone)
        start = now.start_of("week").date()
        end = now.end_of("week").date()
    elif args.date:
        dt = parser.parse_date_only(args.date)
        if dt:
            start = end = dt
        else:
            print(f"❌ 无法识别日期: {args.date}")
            sys.exit(1)
    else:
        # 默认：未来 7 天
        start = date.today()
        end = start + timedelta(days=6)

    # 查询
    if args.category:
        events = query.by_category(args.category, start, end)
        title_suffix = f"[{args.category}]"
    elif args.with_people:
        events = query.by_participant(args.with_people, start, end)
        title_suffix = f"[与{args.with_people}]"
    elif args.search:
        events = query.search(args.search, start, end)
        title_suffix = f"[搜索: {args.search}]"
    else:
        events = query.by_range(start, end)
        title_suffix = ""

    # 构建标题
    date_label = parser.format_date(start)
    if start == end:
        title = f"📅 {date_label} {title_suffix}"
    else:
        end_label = parser.format_date(end)
        title = f"📅 {date_label} ~ {end_label} {title_suffix}"

    render.render_schedule(events, title=title.strip())


# ─── stats 命令 ───────────────────────────────────────────────


def cmd_stats(args):
    """类别聚合统计"""
    config, store, parser, query, agg, render = _build_services()

    period = "week" if args.week else "month"

    # 获取时间范围内的所有事件
    start, end, _ = agg._get_period_range(period)
    all_events = store.get_range(start, end)

    if args.all:
        # 所有类别对比
        categories = list({e.category for e in all_events})
        if not categories:
            print("📊 该时段暂无日程数据")
            return
        results = agg.compare(all_events, categories, period)
        render.render_compare(results)
    else:
        category = args.category or "其他"
        result = agg.summary(all_events, category, period)
        render.render_stats(result)


# ─── delete 命令 ──────────────────────────────────────────────


def cmd_delete(args):
    """删除日程"""
    _, store, _, _, _, _ = _build_services()
    if store.delete(args.event_id):
        print(f"✅ 已删除: {args.event_id}")
    else:
        print(f"❌ 未找到: {args.event_id}")


# ─── render 命令 ──────────────────────────────────────────────


def cmd_render(args):
    """生成日历图片"""
    config, store, parser, query, agg, render = _build_services()

    import pendulum

    now = pendulum.now(config.timezone)

    # 确定时间范围
    if args.range:
        result = parser.parse_range(args.range)
        if result:
            start, end = result
        else:
            print(f"❌ 无法识别范围: {args.range}")
            sys.exit(1)
    elif args.month:
        start = now.start_of("month").date()
        end = now.end_of("month").date()
    else:
        # 默认本周
        start = now.start_of("week").date()
        end = now.end_of("week").date()

    # 输出路径
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.heatmap:
        # ── 热力图模式 ──
        from smart_calendar.render.heatmap_render import HeatmapRender

        heatmap = HeatmapRender(config)
        category = args.heatmap

        all_events = store.get_range(start, end)

        if category == "__all__":
            # 所有类别对比热力图
            categories = list({e.category for e in all_events})
            if not categories:
                print("📊 该时段暂无日程数据")
                return
            period = "month" if args.month else "week"
            results = agg.compare(all_events, categories, period)
            out = output_dir / "heatmap_compare.png"
            heatmap.render_category_comparison(results, out)
            print(f"✅ 类别对比热力图已生成: {out}")
        elif args.year:
            # 全年热力图
            year_start = from_date = pendulum.date(now.year, 1, 1)
            year_end = pendulum.date(now.year, 12, 31)
            year_events = store.get_range(year_start, year_end)
            filtered = [e for e in year_events if e.category == category]
            from collections import Counter

            daily = dict(Counter(e.date for e in filtered))
            icon = config.get_category_icon(category)
            cmap = config.get_category_cmap(category)
            out = output_dir / f"heatmap_{category}_year.png"
            heatmap.render_year(daily, out, year=now.year, title=f"{icon} {now.year}年「{category}」", cmap=cmap)
            print(f"✅ 年度热力图已生成: {out}")
        else:
            # 单月/单周热力图
            period = "month" if args.month else "week"
            result = agg.summary(all_events, category, period)
            out = output_dir / f"heatmap_{category}_{period}.png"
            heatmap.render_month(result, out)
            print(f"✅ 热力图已生成: {out}")

        # 渲染统计文字（对比模式用 compare，单类别用 stats）
        if not args.year:
            period = "month" if args.month else "week"
            if category == "__all__":
                categories = list({e.category for e in all_events})
                results = agg.compare(all_events, categories, period)
                render.render_compare(results)
            else:
                result = agg.summary(all_events, category, period)
                render.render_stats(result)

    else:
        # ── 日历图模式（TOAST UI）──
        from smart_calendar.render.calendar_render import CalendarRender

        cal_render = CalendarRender(config)

        view = args.view or "week"
        events = store.get_range(start, end)

        # focus_date: 视图中心日期
        if view == "month":
            focus = start.replace(day=15)
        elif view == "day" and args.date:
            focus = parser.parse_date_only(args.date) or start
        else:
            focus = start

        date_range_str = f"{parser.format_date(start)} ~ {parser.format_date(end)}"
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
        render.render_schedule(events, title=f"📅 {date_range_str}")

    # 尝试用系统默认应用打开图片
    if args.open:
        import subprocess

        subprocess.run(["open", str(out)], check=False)


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

    # ── delete ──
    p_del = subparsers.add_parser("delete", help="删除日程")
    p_del.add_argument("event_id", help="事件 ID")
    p_del.set_defaults(func=cmd_delete)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
