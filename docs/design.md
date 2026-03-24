# Smart Calendar — 设计文档

> 基于 Markdown 的个人日程管理工具，Obsidian 风格存储，支持人物档案、类别聚合统计、文字/图片双模式输出。

## 1. 项目目标

用最少的胶水代码，把成熟的开源库组合起来，实现：

1. **记录日程** — 几号几点、和谁、做什么，支持中文自然语言输入
2. **人物档案** — 合作人的性格、注意事项、协作备忘
3. **查询日程** — 按时间段、按类别、按人物筛选
4. **类别聚合** — 某类事件本月/本周总次数、每天频率、高峰日
5. **双模式输出** — 终端文字版（rich 表格）+ 图片版（日历图 / 热力图）

## 2. 技术栈

| 模块 | 库 | 版本 | 职责 |
|------|-----|------|------|
| Markdown 存储 | `python-frontmatter` | >=1.1.0 | YAML frontmatter 读写结构化日程 |
| 中文日期解析 | `dateparser` | >=1.2.0 | "下周三下午3点" → datetime |
| 日期计算 | `pendulum` | >=3.0.0 | 时区、范围计算、中文格式化 |
| 日常日历图 | `@toast-ui/calendar` + `playwright` | — | 月/周/日视图 HTML→PNG |
| 总览热力图 | `july` + `matplotlib` | >=0.1.3 | 按类别频率的月度/年度热力图 |
| 终端输出 | `rich` | >=13.0 | 彩色表格、日程列表 |
| HTML 模板 | `jinja2` | >=3.1 | 渲染 TOAST UI 日历页面 |
| 中国节假日 | `chinese-calendar` | >=1.9.0 | 调休、法定假日判断 |

## 3. 目录结构

```
~/Documents/code_project/
├── docs/
│   └── design.md              # 本文档
├── smart_calendar/
│   ├── __init__.py
│   ├── cli.py                 # 命令行入口
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── event_store.py     # 日程 CRUD（frontmatter 读写）
│   │   └── people_store.py    # 人物档案 CRUD
│   ├── parser/
│   │   ├── __init__.py
│   │   └── date_parser.py     # 中文自然语言日期解析
│   ├── query/
│   │   ├── __init__.py
│   │   ├── engine.py          # 按时间/类别/人物筛选
│   │   └── aggregator.py      # 类别聚合统计
│   ├── render/
│   │   ├── __init__.py
│   │   ├── text_render.py     # Rich 终端文字输出
│   │   ├── calendar_render.py # TOAST UI → PNG（日常视图）
│   │   ├── heatmap_render.py  # july 热力图（总览视图）
│   │   └── templates/
│   │       └── toast_ui.html  # TOAST UI Calendar 的 Jinja2 模板
│   └── utils/
│       ├── __init__.py
│       └── holidays.py        # 中国节假日封装
├── data/                      # 用户数据（git 忽略）
│   ├── events/                # 日程文件
│   │   └── 2026/
│   │       └── 03/
│   │           ├── 25.md
│   │           └── 26.md
│   ├── people/                # 人物档案
│   │   ├── 张总.md
│   │   └── 李经理.md
│   └── config.yml             # 事件类别定义 + 颜色映射
├── tests/
│   ├── __init__.py
│   ├── test_storage.py
│   ├── test_parser.py
│   ├── test_query.py
│   └── test_render.py
├── output/                    # 生成的图片（git 忽略）
├── requirements.txt
├── .gitignore
└── README.md
```

## 4. 数据格式

### 4.1 日程文件 (`data/events/2026/03/25.md`)

```markdown
---
date: "2026-03-25"
events:
  - id: "evt_20260325_001"
    time: "14:00-15:30"
    title: "项目进度会"
    category: "会议"
    participants:
      - "张总"
      - "李经理"
    location: "3楼会议室"
    notes: "张总喜欢先看数据，准备好报表"
    priority: "high"
  - id: "evt_20260325_002"
    time: "16:00-17:00"
    title: "代码评审"
    category: "技术"
    participants:
      - "小王"
    notes: ""
    priority: "normal"
---

## 2026-03-25 周三

今天重点是下午的进度会，需要提前准备 Q1 数据报表。
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 自动生成 | `evt_{date}_{seq}` 格式 |
| time | string | 是 | `HH:MM` 或 `HH:MM-HH:MM` |
| title | string | 是 | 事件标题 |
| category | string | 是 | 事件类别，对应 config.yml |
| participants | list[string] | 否 | 参与人，关联 people/ 目录 |
| location | string | 否 | 地点 |
| notes | string | 否 | 备注（如协作注意事项） |
| priority | string | 否 | `high` / `normal` / `low`，默认 `normal` |

### 4.2 人物档案 (`data/people/张总.md`)

```markdown
---
name: "张总"
role: "部门总监"
personality:
  - "结果导向，不喜欢冗长汇报"
  - "喜欢先看数据再讨论"
  - "开会准时，迟到会不高兴"
collaboration_tips:
  - "汇报准备好数据图表"
  - "结论先行，细节备查"
  - "邮件确认会议纪要"
contact: "内线 8001"
tags:
  - "领导"
  - "项目A"
---

## 张总

部门总监，主管项目 A 和项目 B。

### 历史协作记录

- 2026-03-20: 季度汇报，反馈数据呈现方式不错
- 2026-03-15: 项目评审，要求补充竞品分析
```

### 4.3 类别配置 (`data/config.yml`)

```yaml
categories:
  会议:
    color: "#FF6B35"      # 橙色
    icon: "🤝"
    heatmap_cmap: "Oranges"
  技术:
    color: "#4ECDC4"      # 青色
    icon: "💻"
    heatmap_cmap: "Blues"
  学习:
    color: "#45B7D1"      # 蓝色
    icon: "📚"
    heatmap_cmap: "Purples"
  社交:
    color: "#96CEB4"      # 绿色
    icon: "🍻"
    heatmap_cmap: "Greens"
  个人:
    color: "#FFEAA7"      # 黄色
    icon: "🏃"
    heatmap_cmap: "YlOrRd"
  其他:
    color: "#DFE6E9"      # 灰色
    icon: "📌"
    heatmap_cmap: "Greys"

defaults:
  timezone: "Asia/Shanghai"
  locale: "zh"
  work_hours: [9, 18]
  data_dir: "./data"
  output_dir: "./output"
```

## 5. 核心模块设计

### 5.1 存储层 (`storage/`)

```
EventStore                          PeopleStore
├── add(date, time, title, ...)     ├── add(name, personality, ...)
├── get(date) → list[Event]         ├── get(name) → Person
├── update(event_id, **kwargs)      ├── update(name, **kwargs)
├── delete(event_id)                ├── list_all() → list[Person]
└── list_range(start, end)          └── search(keyword) → list[Person]
```

**设计决策：**
- 每天一个 `.md` 文件，按 `data/events/YYYY/MM/DD.md` 组织
- 读写通过 `python-frontmatter`，YAML 部分存结构化数据，Markdown 部分存自由笔记
- 人物档案按 `data/people/{姓名}.md` 存储，一人一文件
- 不引入数据库，文件系统即数据库，grep 即查询

### 5.2 解析层 (`parser/`)

```
DateParser
├── parse(text: str) → datetime          # "下周三下午3点" → datetime
├── parse_range(text: str) → (start, end) # "这周" → (周一, 周日)
└── format(dt: datetime) → str            # datetime → "3月25日 周三 14:00"
```

**解析流程：**

```
用户输入 → dateparser.parse(languages=['zh'])
              │
              ├─ 成功 → 返回 datetime
              └─ 失败 → pendulum 兜底尝试
                          │
                          ├─ 成功 → 返回 datetime
                          └─ 失败 → 提示用户重新输入
```

**支持的中文表达：**

| 输入 | 解析结果 |
|------|---------|
| 下周三下午3点 | 2026-04-01 15:00 |
| 明天上午10点 | 2026-03-25 10:00 |
| 3月28号 | 2026-03-28 |
| 这周五 | 2026-03-27 |
| 后天晚上8点 | 2026-03-26 20:00 |

### 5.3 查询层 (`query/`)

#### 5.3.1 查询引擎 (`engine.py`)

```
QueryEngine
├── by_date(date) → list[Event]
├── by_range(start, end) → list[Event]
├── by_category(category, start?, end?) → list[Event]
├── by_participant(name, start?, end?) → list[Event]
├── upcoming(days=7) → list[Event]
└── search(keyword) → list[Event]     # 全文搜索标题/备注
```

**实现方式：** 遍历时间范围内的 `.md` 文件，用 frontmatter 解析后内存过滤。
数据量级为个人日程（每天 1-10 条），无需索引，直接扫描即可。

#### 5.3.2 聚合引擎 (`aggregator.py`)

```
Aggregator
├── count(category, period='month') → int
├── daily_frequency(category, period='month') → dict[date, int]
├── peak_day(category, period='month') → (weekday, avg_count)
├── summary(category, period='month') → AggResult
└── compare(categories, period='month') → list[AggResult]
```

**AggResult 数据结构：**

```python
@dataclass
class AggResult:
    category: str
    period: str            # "2026年3月" / "3.23-3.29"
    total: int             # 总次数
    daily_counts: dict     # {date: count} → 喂给 july 热力图
    avg_per_day: float     # 日均
    peak_weekday: str      # 高峰星期几
    peak_count: float      # 高峰日均次数
    active_days: int       # 有该事件的天数
    total_days: int        # 统计区间总天数
```

### 5.4 渲染层 (`render/`)

三种渲染器，按需调用：

```
┌──────────────────────────────────────────────────────┐
│                    RenderManager                      │
│  render(events, mode, **kwargs) → str | Path         │
├──────────┬────────────────┬──────────────────────────┤
│ TextRender│ CalendarRender │ HeatmapRender            │
│ (rich)    │ (TOAST UI+PW) │ (july+matplotlib)         │
│           │                │                           │
│ 终端表格   │ 月/周/日 PNG   │ 按类别频率热力图 PNG      │
│ 日程列表   │ 带颜色事件条    │ 月度/年度/GitHub风格      │
└──────────┴────────────────┴──────────────────────────┘
```

#### 5.4.1 文字渲染 (`text_render.py`)

```python
# 日程列表
╭─────────────────────────────────────────╮
│         📅 近期安排 (3.24 - 3.30)        │
├──────────┬──────┬──────────┬────────────┤
│ 日期      │ 时间  │ 事件      │ 参与人     │
├──────────┼──────┼──────────┼────────────┤
│ 3.25 周三 │14:00 │🤝项目进度会│ 张总,李经理 │
│          │16:00 │💻代码评审  │ 小王        │
│ 3.26 周四 │10:00 │📚技术分享  │ 全组        │
│ 3.28 周六 │19:00 │🍻团队聚餐  │ 全组        │
╰──────────┴──────┴──────────┴────────────╯

# 类别聚合统计
╭──────────────────────────────────────╮
│    📊 2026年3月「会议」统计            │
├──────────┬───────┬───────────────────┤
│ 维度      │ 数值  │ 详情              │
├──────────┼───────┼───────────────────┤
│ 本月总计  │ 12 次 │ 3.1 - 3.31       │
│ 本周      │ 3 次  │ 3.23 - 3.29      │
│ 日均      │ 0.5次 │ 有会天数 8 天     │
│ 高峰日    │ 周三  │ 平均 1.5 次/周三  │
│ 占比      │ 35%  │ 占全部事件的比例   │
╰──────────┴───────┴───────────────────╯
```

#### 5.4.2 日历图渲染 (`calendar_render.py`)

**流程：**

```
事件列表 → Jinja2 渲染 TOAST UI HTML → Playwright 截图 → PNG
```

**支持三种视图：**
- `mode='month'` — 月网格，事件显示为彩色条
- `mode='week'` — 周时间网格，按小时分栏
- `mode='day'` — 单日详细视图

**TOAST UI 模板要点：**
- 按 `config.yml` 中的类别颜色渲染事件
- 中文星期/月份
- 标注法定假日和调休日（通过 chinese-calendar）

#### 5.4.3 热力图渲染 (`heatmap_render.py`)

**流程：**

```
聚合结果 (AggResult) → july.heatmap() → PNG
```

**支持的热力图模式：**

| 模式 | 用途 | july 函数 |
|------|------|----------|
| 单月 | 某类别当月频率 | `july.month_plot()` |
| 全年 | 某类别年度分布 | `july.calendar_plot()` |
| GitHub 风格 | 连续活动可视化 | `july.heatmap()` |

**颜色映射：** 每个类别用不同的 matplotlib colormap（在 config.yml 定义），颜色深浅表示当天事件次数。

## 6. CLI 交互设计

```bash
# 添加日程
sc add "下周三下午3点和张总开会，讨论Q1进度"
sc add "明天10点代码评审" --category 技术 --with 小王

# 查询日程
sc show                     # 显示近7天
sc show --week              # 本周
sc show --month             # 本月
sc show --range "3.20-3.31" # 指定范围
sc show --category 会议      # 按类别筛选
sc show --with 张总          # 按人物筛选

# 类别聚合统计
sc stats 会议                # 本月「会议」统计
sc stats 会议 --week         # 本周「会议」统计
sc stats --all               # 所有类别对比

# 生成图片
sc render --week             # 本周日历图 (TOAST UI)
sc render --month            # 本月日历图
sc render --heatmap 会议      # 「会议」频率热力图
sc render --heatmap 会议 --year  # 年度热力图

# 人物档案
sc people add 张总 --role 部门总监
sc people show 张总
sc people note 张总 "喜欢先看数据"

# 输出格式
sc show --format text        # 默认，终端文字
sc show --format image       # 生成图片并打开
sc show --format both        # 文字 + 图片
```

## 7. 实现优先级

### Phase 1: 最小可用（MVP）
1. `storage/event_store.py` — 日程的增/查
2. `parser/date_parser.py` — 中文日期解析
3. `query/engine.py` — 按时间范围查询
4. `render/text_render.py` — Rich 终端文字输出
5. `cli.py` — `add` / `show` 命令

**交付物：** 能通过命令行添加日程、查询近期安排并在终端显示。

### Phase 2: 图片输出
6. `render/calendar_render.py` — TOAST UI 月/周/日 PNG
7. `render/templates/toast_ui.html` — HTML 模板
8. `render/heatmap_render.py` — july 热力图

**交付物：** `sc render` 命令能生成日历图和热力图。

### Phase 3: 高级功能
9. `storage/people_store.py` — 人物档案
10. `query/aggregator.py` — 类别聚合统计
11. `utils/holidays.py` — 节假日标注
12. CLI 补全剩余命令

**交付物：** 完整功能，包括人物档案、类别统计、节假日。

## 8. 依赖安装

```bash
pip install python-frontmatter dateparser pendulum july matplotlib rich chinese-calendar playwright jinja2
playwright install chromium
```

## 9. 设计决策记录

| # | 决策 | 理由 |
|---|------|------|
| D1 | 文件系统存储，不用数据库 | 个人日程量级小；兼容 Obsidian；可 git 版本控制 |
| D2 | 每天一个 .md 文件 | 按日查找 O(1)；避免单文件过大；Obsidian Daily Notes 风格 |
| D3 | TOAST UI 用于日常视图 | 最接近 Google Calendar 体验，月/周/日三视图完整 |
| D4 | july 用于总览/聚合 | 热力图天然适合频率可视化；纯 Python 无需浏览器 |
| D5 | 类别配置集中在 config.yml | 颜色/图标/热力图色系一处定义，全局一致 |
| D6 | CLI 为主要交互方式 | 命令行启动快；可集成到其他工具/脚本；后续可扩展 API |
| D7 | YAML frontmatter + Markdown body | 结构化数据和自由文本并存；Obsidian 原生支持 |
