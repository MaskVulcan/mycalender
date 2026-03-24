"""热力图渲染 — july + matplotlib"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import matplotlib
import matplotlib.cbook

# july 依赖已移除的 MatplotlibDeprecationWarning，做兼容 patch
if not hasattr(matplotlib.cbook, "MatplotlibDeprecationWarning"):
    matplotlib.cbook.MatplotlibDeprecationWarning = matplotlib.MatplotlibDeprecationWarning

import july
import matplotlib.pyplot as plt
import numpy as np

from smart_calendar.query.aggregator import AggResult
from smart_calendar.utils.config import Config

# 使用非交互后端
matplotlib.use("Agg")

# 尝试设置中文字体
_FONT_CANDIDATES = [
    "PingFang SC",
    "Hiragino Sans GB",
    "STHeiti",
    "Arial Unicode MS",
    "Songti SC",
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
]

_CHINESE_FONT: str | None = None


def _find_chinese_font() -> str | None:
    """查找可用的中文字体"""
    global _CHINESE_FONT
    if _CHINESE_FONT is not None:
        return _CHINESE_FONT

    import matplotlib.font_manager as fm

    available = {f.name for f in fm.fontManager.ttflist}
    for font in _FONT_CANDIDATES:
        if font in available:
            _CHINESE_FONT = font
            return font
    _CHINESE_FONT = ""
    return None


def _apply_chinese_font():
    """在每次绘图前强制应用中文字体"""
    font = _find_chinese_font()
    if font:
        plt.rcParams["font.sans-serif"] = [font, "DejaVu Sans"]
        plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False


class HeatmapRender:
    """july 热力图渲染器"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()

    def render_month(
        self,
        agg_result: AggResult,
        output_path: str | Path,
        title: str | None = None,
    ) -> Path:
        """渲染单月热力图"""
        _apply_chinese_font()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmap = self.config.get_category_cmap(agg_result.category)
        icon = self.config.get_category_icon(agg_result.category)

        if title is None:
            title = f"{agg_result.period}「{agg_result.category}」— 共{agg_result.total}次"

        # 准备数据：按日期排序的日期列表和对应计数
        dates_sorted = sorted(agg_result.daily_counts.keys())
        values = [agg_result.daily_counts[d] for d in dates_sorted]

        fig, ax = plt.subplots(figsize=(8, 3))
        july.month_plot(
            dates_sorted,
            values,
            ax=ax,
            cmap=cmap,
            month=dates_sorted[0].month if dates_sorted else 1,
            year=dates_sorted[0].year if dates_sorted else 2026,
            colorbar=True,
            title="",
        )
        # july 会覆盖字体为 monospace，手动用中文字体设置标题
        font = _find_chinese_font()
        fontdict = {"fontname": font, "fontsize": 14} if font else {"fontsize": 14}
        ax.set_title(title, **fontdict, pad=10)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        return output_path

    def render_year(
        self,
        daily_counts: dict[date, int],
        output_path: str | Path,
        year: int | None = None,
        title: str = "",
        cmap: str = "Greens",
    ) -> Path:
        """渲染全年日历热力图"""
        _apply_chinese_font()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if year is None:
            year = date.today().year

        # 填充全年数据
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        all_dates = []
        all_values = []
        current = start
        while current <= end:
            all_dates.append(current)
            all_values.append(daily_counts.get(current, 0))
            current += timedelta(days=1)

        actual_title = title or f"{year}年 事件总览"
        fig, ax = plt.subplots(figsize=(14, 4))
        july.calendar_plot(
            all_dates,
            all_values,
            cmap=cmap,
            title="",
            colorbar=True,
            ax=ax,
        )
        font = _find_chinese_font()
        fontdict = {"fontname": font, "fontsize": 16} if font else {"fontsize": 16}
        fig.suptitle(actual_title, **fontdict)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        return output_path

    def render_github_style(
        self,
        daily_counts: dict[date, int],
        output_path: str | Path,
        title: str = "",
        cmap: str = "Greens",
    ) -> Path:
        """渲染 GitHub 贡献图风格热力图"""
        _apply_chinese_font()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        dates_sorted = sorted(daily_counts.keys())
        values = [daily_counts[d] for d in dates_sorted]

        if not dates_sorted:
            # 空数据保护
            fig, ax = plt.subplots(figsize=(10, 3))
            ax.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=16)
            ax.axis("off")
            fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            return output_path

        actual_title = title or "事件频率"
        fig, ax = plt.subplots(figsize=(10, 3))
        july.heatmap(
            dates_sorted,
            values,
            cmap=cmap,
            title="",
            colorbar=True,
            ax=ax,
        )
        font = _find_chinese_font()
        fontdict = {"fontname": font, "fontsize": 14} if font else {"fontsize": 14}
        ax.set_title(actual_title, **fontdict, pad=10)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        return output_path

    def render_category_comparison(
        self,
        agg_results: list[AggResult],
        output_path: str | Path,
    ) -> Path:
        """渲染多类别热力图对比（纵向排列）"""
        _apply_chinese_font()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        n = len(agg_results)
        if n == 0:
            fig, ax = plt.subplots(figsize=(8, 2))
            ax.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=16)
            ax.axis("off")
            fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            return output_path

        fig, axes = plt.subplots(n, 1, figsize=(8, 2.5 * n))
        if n == 1:
            axes = [axes]

        font = _find_chinese_font()
        fontdict = {"fontname": font, "fontsize": 12} if font else {"fontsize": 12}

        for ax, result in zip(axes, agg_results):
            cmap = self.config.get_category_cmap(result.category)
            dates_sorted = sorted(result.daily_counts.keys())
            values = [result.daily_counts[d] for d in dates_sorted]
            cat_title = f"{result.category} — 共{result.total}次"

            if dates_sorted:
                july.month_plot(
                    dates_sorted,
                    values,
                    ax=ax,
                    cmap=cmap,
                    month=dates_sorted[0].month,
                    year=dates_sorted[0].year,
                    colorbar=True,
                    title="",
                )
                ax.set_title(cat_title, **fontdict, pad=8)
            else:
                ax.set_title(f"{result.category} — 暂无数据", **fontdict)
                ax.axis("off")

        fig.tight_layout()
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        return output_path
