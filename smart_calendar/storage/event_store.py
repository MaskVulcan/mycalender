"""日程存储层 — 基于 Markdown + YAML frontmatter"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

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

    def get(self, dt: date) -> list[Event]:
        """获取某天的全部日程"""
        path = self._date_to_path(dt)
        events_data, _ = self._load_file(path)
        events = [Event.from_dict(e, event_date=dt) for e in events_data]
        # 按时间排序
        events.sort(key=lambda e: (e.start_hour, e.start_minute))
        return events

    def get_range(self, start: date, end: date) -> list[Event]:
        """获取日期范围内的全部日程（含首尾）"""
        from datetime import timedelta

        all_events: list[Event] = []
        current = start
        while current <= end:
            all_events.extend(self.get(current))
            current += timedelta(days=1)
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
        try:
            date_str = event_id.split("_")[1]
            dt = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            for event in self.get(dt):
                if event.id == event_id:
                    return event
        except (IndexError, ValueError):
            pass
        return None
