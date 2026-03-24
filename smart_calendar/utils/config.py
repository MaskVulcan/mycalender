"""配置加载器 — 读取 data/config.yml"""

from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG = {
    "categories": {
        "其他": {
            "color": "#DFE6E9",
            "icon": "📌",
            "heatmap_cmap": "Greys",
        }
    },
    "defaults": {
        "timezone": "Asia/Shanghai",
        "locale": "zh",
        "work_hours": [9, 18],
        "data_dir": "./data",
        "output_dir": "./output",
    },
}


class Config:
    """全局配置，从 config.yml 加载"""

    def __init__(self, base_dir: str | Path | None = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
        self.base_dir = Path(base_dir)
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        config_path = self.base_dir / "data" / "config.yml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        else:
            self._data = _DEFAULT_CONFIG.copy()

    @property
    def categories(self) -> dict[str, dict]:
        return self._data.get("categories", _DEFAULT_CONFIG["categories"])

    @property
    def timezone(self) -> str:
        return self._data.get("defaults", {}).get("timezone", "Asia/Shanghai")

    @property
    def data_dir(self) -> Path:
        rel = self._data.get("defaults", {}).get("data_dir", "./data")
        return self.base_dir / rel

    @property
    def output_dir(self) -> Path:
        rel = self._data.get("defaults", {}).get("output_dir", "./output")
        return self.base_dir / rel

    @property
    def events_dir(self) -> Path:
        return self.data_dir / "events"

    @property
    def people_dir(self) -> Path:
        return self.data_dir / "people"

    def get_category_icon(self, category: str) -> str:
        return self.categories.get(category, {}).get("icon", "📌")

    def get_category_color(self, category: str) -> str:
        return self.categories.get(category, {}).get("color", "#DFE6E9")

    def get_category_cmap(self, category: str) -> str:
        return self.categories.get(category, {}).get("heatmap_cmap", "Greys")

    def list_categories(self) -> list[str]:
        return list(self.categories.keys())
