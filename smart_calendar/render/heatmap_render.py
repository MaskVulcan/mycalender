"""热力图渲染 — july + matplotlib"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import matplotlib
import matplotlib.cbook

# july 依赖已移除的 MatplotlibDeprecationWarning，做兼容 patch
if not hasattr(matplotlib.cbook, "MatplotlibDeprecationWarning"):
    matplotlib.cbook.MatplotlibDeprecationWarning = matplotlib.MatplotlibDeprecationWarning

# 必须在 import matplotlib.pyplot 之前设置非交互后端
matplotlib.use("Agg")

import re
import july
import matplotlib.pyplot as plt

from smart_calendar.query.aggregator import AggResult
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

def _clean_title(title: str) -> str:
    """移除 emoji 等可能导致 matplotlib 乱码的字符"""
    if not title:
        return ""
    return re.sub(r'[^\w\s\u4e00-\u9fa5,.\-—「」\[\]()（）:：]', '', title).strip()

def _create_custom_cmap(base_cmap: str, n_colors: int = 256) -> LinearSegmentedColormap:
    """创建自定义渐变色映射，更柔和美观"""
    base = plt.get_cmap(base_cmap)
    # 添加透明度渐变，让浅色更柔和
    colors = [base(i) for i in np.linspace(0.15, 0.9, n_colors)]
    return LinearSegmentedColormap.from_list('custom', colors)
from smart_calendar.utils.config import Config

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
_FONT_APPLIED: bool = False


def _find_chinese_font() -> str | None:
    """查找可用的中文字体"""
    global _CHINESE_FONT
    if _CHINESE_FONT is not None:
        return _CHINESE_FONT if _CHINESE_FONT else None

    import matplotlib.font_manager as fm

    available = {f.name for f in fm.fontManager.ttflist}
    for font in _FONT_CANDIDATES:
        if font in available:
            _CHINESE_FONT = font
            return font
    _CHINESE_FONT = ""
    return None


def _apply_chinese_font():
    """应用中文字体（仅首次调用时设置 rcParams）"""
    global _FONT_APPLIED
    if _FONT_APPLIED:
        return
    font = _find_chinese_font()
    if font:
        plt.rcParams["font.sans-serif"] = [font, "DejaVu Sans"]
        plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False
    _FONT_APPLIED = True


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
        """渲染单月热力图 - 精美现代风格"""
        _apply_chinese_font()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        base_cmap = self.config.get_category_cmap(agg_result.category)
        icon = self.config.get_category_icon(agg_result.category)

        if title is None:
            title = f"{agg_result.period}「{agg_result.category}」— 共{agg_result.total}次"

        # 准备数据
        dates_sorted = sorted(agg_result.daily_counts.keys())
        if not dates_sorted:
            fig, ax = plt.subplots(figsize=(10, 2))
            ax.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=16, color="#64748b")
            ax.axis("off")
            fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            return output_path

        values = [agg_result.daily_counts[d] for d in dates_sorted]
        year = dates_sorted[0].year
        month = dates_sorted[0].month

        # 创建精美布局
        fig = plt.figure(figsize=(10, 5.5))
        fig.patch.set_facecolor('#f8fafc')
        
        # 使用 GridSpec 创建复杂布局
        ax_card = fig.add_axes([0.05, 0.05, 0.9, 0.9])
        ax_card.set_facecolor('#ffffff')
        ax_card.set_xticks([])
        ax_card.set_yticks([])
        for spine in ax_card.spines.values():
            spine.set_edgecolor('#e2e8f0')
            spine.set_linewidth(1)
            
        gs = fig.add_gridspec(2, 1, height_ratios=[0.15, 0.85], hspace=0.05,
                              left=0.1, right=0.9, top=0.9, bottom=0.1)
        
        # 标题区域
        title_ax = fig.add_subplot(gs[0])
        title_ax.axis("off")
        
        # 热力图区域
        ax = fig.add_subplot(gs[1])
        ax.set_facecolor('#ffffff')
        
        # 绘制热力图
        self._draw_month_heatmap(ax, year, month, dates_sorted, values, base_cmap)
        
        # 设置标题
        font = _find_chinese_font()
        safe_title = _clean_title(title)
        title_ax.text(0.0, 0.5, safe_title, transform=title_ax.transAxes,
                     fontsize=18, fontweight="bold", color="#0f172a",
                     ha="left", va="center", fontname=font if font else None)
        
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)

        return output_path
    
    def _draw_month_heatmap(self, ax, year: int, month: int, dates, values, base_cmap: str):
        """绘制精美的月度热力图（圆角方块）"""
        import calendar
        from matplotlib.patches import FancyBboxPatch
        
        # 计算该月第一天是星期几（0=周一，6=周日）
        first_weekday = calendar.weekday(year, month, 1)
        month_days = calendar.monthrange(year, month)[1]
        
        # 创建数据网格（行=周，列=星期）
        weeks = (first_weekday + month_days + 6) // 7
        
        ax.set_xlim(-0.5, 7.5)
        ax.set_ylim(weeks + 0.5, -0.8)
        ax.axis('off')
        
        max_val = max(values) if values else 1
        cmap = _create_custom_cmap(base_cmap)
        date_to_value = dict(zip(dates, values))
        
        # 星期标签
        weekdays = ['一', '二', '三', '四', '五', '六', '日']
        for i, wd in enumerate(weekdays):
            ax.text(i + 0.5, -0.3, wd, ha='center', va='center', fontsize=12, fontweight='500', color='#64748b')
            
        # 周标签
        for i in range(weeks):
            ax.text(-0.1, i + 0.5, f'W{i+1}', ha='right', va='center', fontsize=11, color='#94a3b8')
            
        # 绘制格子
        for day in range(1, month_days + 1):
            row = (first_weekday + day - 1) // 7
            col = (first_weekday + day - 1) % 7
            d = date(year, month, day)
            val = date_to_value.get(d, 0)
            
            color = '#f1f5f9' if val == 0 else cmap(0.2 + 0.8 * (val / max_val))
            
            rect = FancyBboxPatch(
                (col + 0.1, row + 0.1), 0.8, 0.8,
                boxstyle="round,pad=0.02,rounding_size=0.15",
                facecolor=color, edgecolor='none'
            )
            ax.add_patch(rect)
            
            text_color = '#94a3b8' if val == 0 else ('#ffffff' if val > max_val * 0.4 else '#1e293b')
            ax.text(col + 0.5, row + 0.5, str(day), ha='center', va='center',
                   fontsize=11, fontweight='600', color=text_color)
                   
        # 图例
        legend_x = 6.5
        legend_y = weeks + 0.2
        ax.text(legend_x - 2.5, legend_y, '少', ha='right', va='center', fontsize=10, color='#94a3b8')
        for i, ratio in enumerate([0, 0.25, 0.5, 0.75, 1.0]):
            c = '#f1f5f9' if i == 0 else cmap(0.2 + 0.8 * ratio)
            rect = FancyBboxPatch(
                (legend_x - 2.3 + i*0.4, legend_y - 0.15), 0.3, 0.3,
                boxstyle="round,pad=0.01,rounding_size=0.05",
                facecolor=c, edgecolor='none'
            )
            ax.add_patch(rect)
        ax.text(legend_x - 2.3 + 5*0.4, legend_y, '多', ha='left', va='center', fontsize=10, color='#94a3b8')

    def render_year(
        self,
        daily_counts: dict[date, int],
        output_path: str | Path,
        year: int | None = None,
        title: str = "",
        cmap: str = "Greens",
    ) -> Path:
        """渲染全年日历热力图 - GitHub 风格"""
        _apply_chinese_font()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if year is None:
            year = date.today().year

        actual_title = title or f"{year}年 事件总览"
        
        # 创建精美布局
        fig = plt.figure(figsize=(14, 4.5))
        fig.patch.set_facecolor('#f8fafc')
        
        ax_card = fig.add_axes([0.03, 0.05, 0.94, 0.9])
        ax_card.set_facecolor('#ffffff')
        ax_card.set_xticks([])
        ax_card.set_yticks([])
        for spine in ax_card.spines.values():
            spine.set_edgecolor('#e2e8f0')
            spine.set_linewidth(1)
            
        gs = fig.add_gridspec(2, 1, height_ratios=[0.2, 0.8], hspace=0.05,
                              left=0.06, right=0.94, top=0.88, bottom=0.15)
        
        # 标题区域
        title_ax = fig.add_subplot(gs[0])
        title_ax.axis("off")
        
        # 热力图区域
        ax = fig.add_subplot(gs[1])
        ax.set_facecolor('#ffffff')
        
        # 绘制 GitHub 风格热力图
        self._draw_year_heatmap(ax, year, daily_counts, cmap)
        
        # 设置标题
        font = _find_chinese_font()
        safe_title = _clean_title(actual_title)
        title_ax.text(0.0, 0.5, safe_title, transform=title_ax.transAxes,
                     fontsize=20, fontweight="bold", color="#0f172a",
                     ha="left", va="center", fontname=font if font else None)
        
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)

        return output_path
    
    def _draw_year_heatmap(self, ax, year: int, daily_counts: dict[date, int], base_cmap: str):
        """绘制 GitHub 风格的年度热力图（圆角方块）"""
        import calendar
        from matplotlib.patches import FancyBboxPatch
        
        first_day = date(year, 1, 1)
        last_day = date(year, 12, 31)
        
        # 计算从周一开始的第一周
        first_weekday = first_day.weekday()  # 0=周一
        
        # 总周数（最多 53 周）
        total_days = (last_day - first_day).days + 1
        total_weeks = (first_weekday + total_days + 6) // 7
        
        ax.set_xlim(-1.5, total_weeks + 1)
        ax.set_ylim(7.5, -1.5)
        ax.axis('off')
        
        max_val = max(daily_counts.values()) if daily_counts else 1
        cmap = _create_custom_cmap(base_cmap)
        
        # 星期标签
        weekdays = ['一', '二', '三', '四', '五', '六', '日']
        for i in [0, 2, 4]:
            ax.text(-0.3, i + 0.5, weekdays[i], ha='right', va='center', fontsize=10, color='#94a3b8')
            
        # 月份标签
        months = ['1月', '2月', '3月', '4月', '5月', '6月', 
                 '7月', '8月', '9月', '10月', '11月', '12月']
        month_positions = []
        
        for month_idx, month_name in enumerate(months):
            month_start = date(year, month_idx + 1, 1)
            if month_start < first_day:
                continue
            week_num = (first_weekday + (month_start - first_day).days) // 7
            if week_num < total_weeks:
                month_positions.append((week_num, month_name))
        
        # 只显示部分月份标签（避免重叠）
        step = max(1, len(month_positions) // 6)
        for i, (pos, label) in enumerate(month_positions):
            if i % step == 0:
                ax.text(pos + 0.5, -0.5, label, ha='center', va='center', fontsize=11, color='#64748b', fontweight='500')
                
        # 绘制格子
        current = first_day
        while current <= last_day:
            weekday = current.weekday()  # 0=周一
            week_num = (first_weekday + (current - first_day).days) // 7
            val = daily_counts.get(current, 0)
            
            color = '#f1f5f9' if val == 0 else cmap(0.2 + 0.8 * (val / max_val))
            
            rect = FancyBboxPatch(
                (week_num + 0.1, weekday + 0.1), 0.8, 0.8,
                boxstyle="round,pad=0.02,rounding_size=0.2",
                facecolor=color, edgecolor='none'
            )
            ax.add_patch(rect)
            current += timedelta(days=1)
            
        # 图例
        legend_x = total_weeks - 1
        legend_y = 7.8
        ax.text(legend_x - 2.5, legend_y, '少', ha='right', va='center', fontsize=10, color='#94a3b8')
        for i, ratio in enumerate([0, 0.25, 0.5, 0.75, 1.0]):
            c = '#f1f5f9' if i == 0 else cmap(0.2 + 0.8 * ratio)
            rect = FancyBboxPatch(
                (legend_x - 2.3 + i*0.4, legend_y - 0.15), 0.3, 0.3,
                boxstyle="round,pad=0.01,rounding_size=0.05",
                facecolor=c, edgecolor='none'
            )
            ax.add_patch(rect)
        ax.text(legend_x - 2.3 + 5*0.4, legend_y, '多', ha='left', va='center', fontsize=10, color='#94a3b8')

    def render_github_style(
        self,
        daily_counts: dict[date, int],
        output_path: str | Path,
        title: str = "",
        cmap: str = "Greens",
    ) -> Path:
        """渲染 GitHub 贡献图风格热力图"""
        # 复用 render_year 实现
        return self.render_year(daily_counts, output_path, title=title, cmap=cmap)

    def render_category_comparison(
        self,
        agg_results: list[AggResult],
        output_path: str | Path,
    ) -> Path:
        """渲染多类别热力图对比 - 精美卡片式布局"""
        _apply_chinese_font()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        n = len(agg_results)
        if n == 0:
            fig, ax = plt.subplots(figsize=(10, 3))
            ax.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=16, color="#64748b")
            ax.axis("off")
            fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            return output_path

        # 创建精美布局
        fig = plt.figure(figsize=(10, 4.5 * n))
        fig.patch.set_facecolor('#f8fafc')
        
        # 使用 GridSpec 创建复杂布局
        gs = fig.add_gridspec(n, 1, hspace=0.3)
        
        font = _find_chinese_font()
        
        for idx, result in enumerate(agg_results):
            # 创建卡片背景
            ax_wrapper = fig.add_subplot(gs[idx])
            ax_wrapper.set_facecolor('#ffffff')
            
            # 添加卡片边框
            for spine in ax_wrapper.spines.values():
                spine.set_edgecolor('#e2e8f0')
                spine.set_linewidth(1)
                spine.set_visible(True)
            
            ax_wrapper.set_xticks([])
            ax_wrapper.set_yticks([])
            
            # 在卡片内部创建热力图
            inner_gs = gs[idx].subgridspec(2, 1, height_ratios=[0.2, 0.8], hspace=0.05)
            
            # 标题区域
            title_ax = fig.add_subplot(inner_gs[0])
            title_ax.axis("off")
            title_ax.set_facecolor('#ffffff')
            
            # 热力图区域
            ax = fig.add_subplot(inner_gs[1])
            ax.set_facecolor('#ffffff')
            
            base_cmap = self.config.get_category_cmap(result.category)
            dates_sorted = sorted(result.daily_counts.keys())
            values = [result.daily_counts[d] for d in dates_sorted]
            
            cat_title = f"{result.category} — 共{result.total}次"
            safe_title = _clean_title(cat_title)
            
            # 设置标题
            title_ax.text(0.05, 0.5, safe_title, transform=title_ax.transAxes,
                         fontsize=14, fontweight="bold", color="#0f172a",
                         ha="left", va="center", fontname=font if font else None)
            
            if dates_sorted:
                year = dates_sorted[0].year
                month = dates_sorted[0].month
                self._draw_month_heatmap(ax, year, month, dates_sorted, values, base_cmap)
            else:
                ax.text(0.5, 0.5, "暂无数据", transform=ax.transAxes,
                       ha="center", va="center", fontsize=14, color="#94a3b8")
                ax.axis("off")
        
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)

        return output_path
