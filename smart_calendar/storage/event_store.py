"""日程存储层 — 基于 Markdown + YAML frontmatter"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path

import frontmatter


@dataclass
class Event:
    """单条日程事件"""

    id: str
    date: date
    time: str  # "HH:MM" 或 "HH:MM-HH:MM"
    title: str
    category: str = "其他"
    participants: list[str] = field(default_factory=list)
    location: str = ""
    notes: str = ""
    priority: str = "normal"  # high / normal / low

    @property
    def start_hour(self) -> int:
        """提取起始小时，用于排序"""
        try:
            return int(self.time.split(":")[0])
        except (ValueError, IndexError):
            return 0

    @property
    def start_minute(self) -> int:
        try:
            return int(self.time.split(":")[1].split("-")[0])
        except (ValueError, IndexError):
            return 0

    def to_dict(self) -> dict:
        """序列化为 YAML 可存储的 dict"""
        d = asdict(self)
        d["date"] = self.date.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict, event_date: date | None = None) -> Event:
        """从 YAML dict 反序列化"""
        d = data.copy()
        if "date" in d and isinstance(d["date"], str):
            d["date"] = date.fromisoformat(d["date"])
        elif event_date:
            d["date"] = event_date
        if "participants" not in d:
            d["participants"] = []
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _generate_id(dt: date) -> str:
    """生成事件 ID: evt_YYYYMMDD_xxxx"""
    short = uuid.uuid4().hex[:6]
    return f"evt_{dt.strftime('%Y%m%d')}_{short}"


class EventStore:
    """日程文件读写，一天一个 .md 文件"""

    def __init__(self, events_dir: str | Path):
        self.events_dir = Path(events_dir)

    def _date_to_path(self, dt: date) -> Path:
        """date → data/events/YYYY/MM/DD.md"""
        return self.events_dir / str(dt.year) / f"{dt.month:02d}" / f"{dt.day:02d}.md"

    def _ensure_dir(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)

    def _load_file(self, path: Path) -> tuple[list[dict], str]:
        """加载一个 .md 文件，返回 (events_list, markdown_body)"""
        if not path.exists():
            return [], ""
        post = frontmatter.load(str(path))
        events = post.metadata.get("events", [])
        return events, post.content

    def _save_file(self, path: Path, events: list[dict], body: str = ""):
        """保存 events 到 .md 文件"""
        self._ensure_dir(path)
        post = frontmatter.Post(body)
        post.metadata["events"] = events
        if events:
            # 从第一个事件提取日期写入 metadata
            post.metadata["date"] = events[0].get("date", "")
        content = frontmatter.dumps(post)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def add(self, event: Event) -> Event:
        """添加一条日程，返回带 ID 的 Event"""
        if not event.id:
            event.id = _generate_id(event.date)

        path = self._date_to_path(event.date)
        events, body = self._load_file(path)
        events.append(event.to_dict())
        self._save_file(path, events, body)
        return event

    def find_conflicts(self, event_date: date, time_str: str) -> list[Event]:
        """检查指定日期和时间段是否与已有日程冲突。

        Args:
            event_date: 事件日期
            time_str: 时间字符串，如 "14:00" 或 "14:00-15:30"

        Returns:
            重叠的已有日程列表
        """
        existing = self.get(event_date)
        if not existing:
            return []

        # 解析新事件的起止分钟数
        new_start, new_end = self._parse_time_range(time_str)
        if new_start is None:
            return []

        conflicts = []
        for e in existing:
            e_start, e_end = self._parse_time_range(e.time)
            if e_start is None:
                continue
            # 两个时间段有重叠的条件
            if new_start < e_end and new_end > e_start:
                conflicts.append(e)
        return conflicts

    @staticmethod
    def _parse_time_range(time_str: str) -> tuple[int | None, int | None]:
        """将时间字符串解析为 (开始分钟数, 结束分钟数)。

        "14:00" → (840, 900)        # 默认 1 小时
        "14:00-15:30" → (840, 930)
        """
        parts = time_str.split("-")
        try:
            h, m = (int(x) for x in parts[0].strip().split(":"))
            start_min = h * 60 + m
        except (ValueError, IndexError):
            return None, None

        if len(parts) > 1:
            try:
                eh, em = (int(x) for x in parts[1].strip().split(":"))
                end_min = eh * 60 + em
            except (ValueError, IndexError):
                end_min = start_min + 60
        else:
            end_min = start_min + 60

        return start_min, end_min

    def get(self, dt: date) -> list[Event]:
        """获取某天的全部日程"""
        path = self._date_to_path(dt)
        events_data, _ = self._load_file(path)
        events = [Event.from_dict(e, event_date=dt) for e in events_data]
        # 按时间排序
        events.sort(key=lambda e: (e.start_hour, e.start_minute))
        return events

    def get_range(self, start: date, end: date) -> list[Event]:
        """获取日期范围内的全部日程（含首尾），只遍历涉及的年/月目录"""
        all_events: list[Event] = []

        # 按年月剪枝：只遍历 start~end 涉及的 YYYY/MM 目录
        current = start.replace(day=1)
        visited_months: set[tuple[int, int]] = set()
        while current <= end:
            ym = (current.year, current.month)
            if ym not in visited_months:
                visited_months.add(ym)
                month_dir = self.events_dir / str(current.year) / f"{current.month:02d}"
                if month_dir.is_dir():
                    for md_path in sorted(month_dir.glob("*.md")):
                        try:
                            day = int(md_path.stem)
                            file_date = date(current.year, current.month, day)
                        except (ValueError, IndexError):
                            continue
                        if start <= file_date <= end:
                            events_data, _ = self._load_file(md_path)
                            events = [Event.from_dict(e, event_date=file_date) for e in events_data]
                            events.sort(key=lambda e: (e.start_hour, e.start_minute))
                            all_events.extend(events)
            # 跳到下个月
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        # 按日期 + 时间排序
        all_events.sort(key=lambda e: (e.date, e.start_hour, e.start_minute))
        return all_events

    def update(self, event_id: str, **kwargs) -> Event | None:
        """按 ID 更新日程字段"""
        event = self._find_by_id(event_id)
        if not event:
            return None

        path = self._date_to_path(event.date)
        events_data, body = self._load_file(path)

        for e in events_data:
            if e.get("id") == event_id:
                for k, v in kwargs.items():
                    e[k] = v
                break

        self._save_file(path, events_data, body)
        return Event.from_dict(
            next(e for e in events_data if e.get("id") == event_id),
            event_date=event.date,
        )

    def delete(self, event_id: str) -> bool:
        """按 ID 删除日程"""
        event = self._find_by_id(event_id)
        if not event:
            return False

        path = self._date_to_path(event.date)
        events_data, body = self._load_file(path)
        events_data = [e for e in events_data if e.get("id") != event_id]

        if events_data:
            self._save_file(path, events_data, body)
        elif path.exists():
            path.unlink()

        return True

    def _find_by_id(self, event_id: str) -> Event | None:
        """根据 ID 查找事件（从 ID 提取日期缩小搜索范围）"""
        # ID 格式: evt_YYYYMMDD_xxxx
        if not re.match(r"^evt_\d{8}_[a-f0-9]+$", event_id):
            return None

        try:
            date_str = event_id.split("_")[1]
            dt = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            for event in self.get(dt):
                if event.id == event_id:
                    return event
        except (IndexError, ValueError):
            pass
        return None
