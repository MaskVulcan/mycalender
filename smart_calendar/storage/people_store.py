"""人物档案存储层 — 基于 Markdown + YAML frontmatter"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

import frontmatter


@dataclass
class Person:
    """人物档案"""

    name: str
    role: str = ""
    personality: list[str] = field(default_factory=list)
    collaboration_tips: list[str] = field(default_factory=list)
    contact: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""  # Markdown body 自由笔记

    def to_dict(self) -> dict:
        """序列化为 YAML 可存储的 dict（不含 notes，notes 存在 body 中）"""
        d = asdict(self)
        del d["notes"]
        return d

    @classmethod
    def from_post(cls, post: frontmatter.Post) -> Person:
        """从 frontmatter Post 反序列化"""
        meta = post.metadata
        return cls(
            name=meta.get("name", ""),
            role=meta.get("role", ""),
            personality=meta.get("personality", []),
            collaboration_tips=meta.get("collaboration_tips", []),
            contact=meta.get("contact", ""),
            tags=meta.get("tags", []),
            notes=post.content,
        )


class PeopleStore:
    """人物档案文件读写，一人一个 .md 文件"""

    def __init__(self, people_dir: str | Path):
        self.people_dir = Path(people_dir)
        self.people_dir.mkdir(parents=True, exist_ok=True)

    def _name_to_path(self, name: str) -> Path:
        """name → data/people/{name}.md"""
        # 文件名安全处理：保留中文，替换特殊字符
        safe_name = name.replace("/", "_").replace("\\", "_").strip()
        return self.people_dir / f"{safe_name}.md"

    def _save(self, person: Person):
        """保存人物档案"""
        post = frontmatter.Post(person.notes)
        post.metadata.update(person.to_dict())
        content = frontmatter.dumps(post)
        with open(self._name_to_path(person.name), "w", encoding="utf-8") as f:
            f.write(content)

    def add(self, person: Person) -> Person:
        """添加人物档案"""
        self._save(person)
        return person

    def get(self, name: str) -> Person | None:
        """获取人物档案"""
        path = self._name_to_path(name)
        if not path.exists():
            return None
        post = frontmatter.load(str(path))
        return Person.from_post(post)

    def update(self, name: str, **kwargs) -> Person | None:
        """更新人物档案字段"""
        person = self.get(name)
        if not person:
            return None

        for k, v in kwargs.items():
            if hasattr(person, k):
                setattr(person, k, v)

        self._save(person)
        return person

    def add_personality(self, name: str, trait: str) -> Person | None:
        """追加一条性格特征"""
        person = self.get(name)
        if not person:
            return None
        if trait not in person.personality:
            person.personality.append(trait)
            self._save(person)
        return person

    def add_tip(self, name: str, tip: str) -> Person | None:
        """追加一条协作建议"""
        person = self.get(name)
        if not person:
            return None
        if tip not in person.collaboration_tips:
            person.collaboration_tips.append(tip)
            self._save(person)
        return person

    def add_note(self, name: str, note: str) -> Person | None:
        """追加自由笔记（附加到 Markdown body）"""
        person = self.get(name)
        if not person:
            return None
        if person.notes:
            person.notes += f"\n\n{note}"
        else:
            person.notes = note
        self._save(person)
        return person

    def list_all(self) -> list[Person]:
        """列出所有人物档案"""
        persons = []
        for path in sorted(self.people_dir.glob("*.md")):
            post = frontmatter.load(str(path))
            persons.append(Person.from_post(post))
        return persons

    def search(self, keyword: str) -> list[Person]:
        """搜索人物（姓名、角色、标签）"""
        keyword_lower = keyword.lower()
        results = []
        for person in self.list_all():
            if (
                keyword_lower in person.name.lower()
                or keyword_lower in person.role.lower()
                or any(keyword_lower in t.lower() for t in person.tags)
                or any(keyword_lower in p.lower() for p in person.personality)
            ):
                results.append(person)
        return results

    def delete(self, name: str) -> bool:
        """删除人物档案"""
        path = self._name_to_path(name)
        if path.exists():
            path.unlink()
            return True
        return False
