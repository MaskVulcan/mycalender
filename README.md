# Smart Calendar

基于 Markdown 的个人日程管理工具。Obsidian 风格存储，支持中文自然语言输入、人物档案、类别聚合统计、终端文字 + 图片双模式输出。

## 安装

```bash
cd mycalendar
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
playwright install chromium   # 日历图渲染需要
```

安装完成后即可使用 `sc` 命令：

```bash
sc --help
```

## 快速上手

### 添加日程

```bash
# 自然语言输入
sc add 明天下午3点和张总开会讨论Q1进度
sc add 后天晚上8点团队聚餐 --category 社交 --with 全组

# 指定详细参数
sc add 代码评审 --date 2026-03-25 --time 10:00-11:00 --category 技术 --with 小王
```

### 查看日程

```bash
sc show                       # 未来 7 天
sc show --week                # 本周
sc show --month               # 本月
sc show --range "3.20-3.31"   # 指定范围
sc show --category 会议        # 按类别筛选
sc show --with 张总            # 按参与人筛选
sc show --search 评审          # 关键字搜索
```

查看日程时，已知参与人的性格特征和协作建议会自动显示在表格下方。

### 类别统计

```bash
sc stats 会议               # 本月「会议」统计
sc stats 会议 --week        # 本周统计
sc stats --all              # 所有类别对比
```

### 生成图片

```bash
# TOAST UI 日历图
sc render                   # 本周周视图
sc render --view month      # 月视图
sc render --view day --date 明天  # 日视图

# 热力图
sc render --heatmap 会议           # 本周「会议」频率热力图
sc render --heatmap 会议 --month   # 本月热力图
sc render --heatmap 会议 --year    # 年度热力图
sc render --heatmap __all__ --month  # 所有类别对比热力图

# 生成后自动打开
sc render --open
```

### 人物档案

```bash
# 创建档案
sc people add 张总 --role "技术VP" --personality "果断,注重效率" --tips "准备好数据,发言简洁" --tags "管理层"

# 查看档案（同时展示近期相关日程）
sc people show 张总

# 追加备注
sc people note 张总 上次开会提到想推进微服务
sc people note 张总 --as-personality 开会喜欢直奔主题
sc people note 张总 --as-tip 会议材料提前一天发

# 列出 / 搜索
sc people list
sc people list 管理

# 更新 / 删除
sc people update 张总 --contact "zhang@example.com"
sc people delete 张总
```

### 删除日程

```bash
sc delete evt_20260325_abc123
```

## 项目结构

```
mycalendar/
├── smart_calendar/
│   ├── cli.py                  # 命令行入口 (sc 命令)
│   ├── storage/
│   │   ├── event_store.py      # 日程 CRUD (Markdown + YAML frontmatter)
│   │   └── people_store.py     # 人物档案 CRUD
│   ├── parser/
│   │   └── date_parser.py      # 中文自然语言日期解析
│   ├── query/
│   │   ├── engine.py           # 按时间/类别/人物筛选
│   │   └── aggregator.py       # 类别聚合统计
│   ├── render/
│   │   ├── text_render.py      # Rich 终端文字输出
│   │   ├── calendar_render.py  # TOAST UI Calendar → PNG
│   │   ├── heatmap_render.py   # july 热力图
│   │   └── templates/
│   │       └── toast_ui.html   # TOAST UI Jinja2 模板
│   └── utils/
│       ├── config.py           # 配置加载
│       └── holidays.py         # 中国节假日封装
├── data/
│   ├── config.yml              # 类别定义 + 颜色配置
│   ├── events/                 # 日程文件 (YYYY/MM/DD.md)
│   └── people/                 # 人物档案 ({姓名}.md)
├── tests/                      # pytest 单元测试
├── output/                     # 生成的图片
└── docs/
    └── design.md               # 设计文档
```

## 数据格式

### 日程文件 (`data/events/2026/03/25.md`)

```yaml
---
events:
  - id: "evt_20260325_abc123"
    time: "14:00-15:30"
    title: "项目进度会"
    category: "会议"
    participants: ["张总", "李经理"]
    location: "3楼会议室"
    notes: "准备好Q1数据"
    priority: "high"
---
```

### 人物档案 (`data/people/张总.md`)

```yaml
---
name: "张总"
role: "技术VP"
personality: ["果断", "注重效率"]
collaboration_tips: ["准备好数据", "发言简洁"]
contact: "zhang@example.com"
tags: ["管理层"]
---

自由格式的备忘笔记...
```

## 技术栈

| 库 | 用途 |
|----|------|
| `python-frontmatter` | Markdown + YAML 读写 |
| `dateparser` + `pendulum` | 中文自然语言日期解析 |
| `rich` | 终端彩色表格 |
| `@toast-ui/calendar` + `playwright` | 日历图 HTML → PNG |
| `july` + `matplotlib` | 频率热力图 |
| `chinese-calendar` | 中国节假日/调休判断 |
| `jinja2` | HTML 模板渲染 |

## 运行测试

```bash
pip install pytest
python -m pytest tests/ -v
```
