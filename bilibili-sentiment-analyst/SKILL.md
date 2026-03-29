---
name: bilibili-sentiment-analyst
description: B站(Bilibili)游戏视频评论区与弹幕的全量采集及深度舆情分析技能包。通过B站公开Web API批量拉取指定视频或UP主的评论和弹幕数据，结合LDA主题模型、弹幕密度峰值分析、三连互动分层分析等方法，输出结构化的舆情分析报告。支持三种入口：(1)关键词话题搜索（如"鸣潮1.4"→自动搜索Top N视频→批量采集评论弹幕→汇总分析）；(2)指定视频BV号/av号深度分析；(3)UP主UID批量视频分析。当用户提到"B站分析"、"Bilibili舆情"、"B站评论分析"、"B站弹幕分析"、"分析B站玩家讨论"、"B站上关于XX的讨论"、"B站话题分析"、或给出B站视频链接/BV号/UP主并要求分析时，使用此技能。也适用于竞品B站口碑对比、版本PV评论区舆情、游戏区UP主内容追踪等场景。
---

# Bilibili Sentiment Analyst

## 概述

通过B站公开Web API全量拉取视频评论与弹幕，执行多维度量化分析，输出带结论的舆情报告。

**核心能力**：
- **关键词搜索 + 批量采集**（话题分析模式——不需要指定视频）
- 全量采集指定视频的评论与弹幕（无需API Key）
- 批量采集指定UP主的近期视频列表
- LDA主题聚类（自动发现玩家讨论热点）
- 弹幕密度峰值分析（B站独有——定位视频中的情绪爆发点）
- 三连互动分层分析（点赞/投币/收藏的差异化解读——B站独有）
- 评论情感倾向分析（正面/负面/中性）
- 关键词声量份额统计
- 真实评论与弹幕原文佐证提取
- 多视频横向对比

## 环境要求

### Python依赖
```bash
pip install -r <skill-dir>/references/requirements.txt
```

核心依赖：requests, pandas, scikit-learn, jieba, nltk, langdetect, openpyxl, numpy, google-protobuf

### API认证
**无需API Key。** B站大部分Web API为公开接口，可直接调用。

可选：登录态Cookie可获取更完整的数据（如长评论、会员弹幕等），将Cookie存入 `.env`：
```
BILIBILI_COOKIE=你的浏览器Cookie（可选）
```

## 工作流程

### Step 1：确定分析模式

根据用户输入判断使用哪种模式：

| 用户输入 | 分析模式 | 入口方法 |
|---------|---------|----------|
| 关键词/话题（如"鸣潮1.4"、"原神开放世界"） | **话题搜索模式** | `search_and_collect()` |
| BV号 / av号 / 视频URL | **单视频分析** | `get_video_info()` + `fetch_comments()` |
| UP主主页链接或UID | **UP主批量分析** | `fetch_user_videos()` |

支持的输入格式：
- BV号：`BV1xx411c7mD`
- 完整URL：`https://www.bilibili.com/video/BV1xx411c7mD`
- av号：`av170001`
- UP主主页链接或UID（批量采集该UP主视频）
- **纯文本关键词**（触发话题搜索模式）

### Step 2：数据采集

运行采集脚本：
```python
import sys
sys.path.append(r"<skill-dir>/scripts")
from bilibili_scraper import BilibiliScraper

scraper = BilibiliScraper()
```

#### 模式A：话题搜索模式（推荐 —— 不需要指定视频）

用于广泛了解某个话题的B站讨论情况：

```python
# 一站式：搜索 + 批量拉取Top N视频的评论+弹幕
result = scraper.search_and_collect(
    keyword="鸣潮1.4",         # 搜索关键词
    top_n=10,                    # 取搜索结果前N个视频深入分析
    search_order="totalrank",    # 综合排序（推荐）
    tids=4,                      # 限定游戏区（0=全部）
    comment_pages=3,             # 每个视频拉取的评论页数
    fetch_danmaku=True,          # 是否拉取弹幕
)

# result["videos"] 是一个列表，每个元素包含:
#   video_info: 视频详情
#   comments: 评论数据
#   danmaku: 弹幕数据
#   search_meta: 搜索排名、播放量、标签
```

**搜索参数说明**：

| 参数 | 可选值 | 说明 |
|------|---------|------|
| `search_order` | `totalrank`(default), `click`, `pubdate`, `dm`, `stow`, `scores` | 综合/播放/最新/弹幕/收藏/评论 |
| `tids` | `0`=全部, `4`=游戏区, `17`=单机, `171`=电竞, `172`=手游, `65`=网游 | 分区筛选 |
| `duration` | `0`=全部, `1`=0-10min, `2`=10-30min, `3`=30-60min, `4`=60+min | 时长筛选 |
| `top_n` | 建议5-15 | 太少样本不足，太多采集慢 |

#### 模式B：单视频分析

```python
# 获取视频基础信息
video_info = scraper.get_video_info("BV1xx411c7mD")

# 拉取评论（全量）
comments = scraper.fetch_comments(
    video_id="BV1xx411c7mD",    # BV号或aid
    sort=2,                      # 0=按时间, 1=按点赞数, 2=按回复数
    max_pages=None,              # None=全量，或指定页数
)

# 拉取弹幕（全量，基于protobuf接口）
danmakus = scraper.fetch_danmaku(
    cid=video_info["cid"],       # 视频的cid（从video_info获取）
)
```

#### 模式C：UP主批量分析

```python
# 获取UP主视频列表
up_videos = scraper.fetch_user_videos(
    mid=12345678,                # UP主UID
    max_pages=5,                 # 最多采集页数（每页30条）
)
```

采集字段说明见 `references/api-reference.md`

### Step 3：数据分析

#### 话题搜索模式的分析（多视频汇总）

当使用 `search_and_collect()` 采集后，需要将多个视频的评论+弹幕汇总分析：

```python
from bilibili_analyst import BilibiliAnalyst
import pandas as pd

analyst = BilibiliAnalyst()

# 汇总多视频的评论和弹幕
all_comment_dfs = []
all_danmaku_dfs = []
all_video_infos = []

for item in result["videos"]:
    vi = item["video_info"]
    all_video_infos.append(vi)

    df_c, df_d = analyst.load_data(item["comments"], item["danmaku"])
    # 标记来源视频
    if not df_c.empty:
        df_c["source_bvid"] = vi["bvid"]
        df_c["source_title"] = vi["title"]
        all_comment_dfs.append(df_c)
    if not df_d.empty:
        df_d["source_bvid"] = vi["bvid"]
        df_d["source_title"] = vi["title"]
        all_danmaku_dfs.append(df_d)

df_comments = pd.concat(all_comment_dfs, ignore_index=True) if all_comment_dfs else pd.DataFrame()
df_danmaku = pd.concat(all_danmaku_dfs, ignore_index=True) if all_danmaku_dfs else pd.DataFrame()

# LDA主题分析（汇总后的全部评论）
topics = analyst.run_lda(df_comments, language="auto", n_topics="auto")

# 关键词声量统计
sov = analyst.share_of_voice(df_comments, df_danmaku, keywords={
    "画质": ["画质", "画面", "建模", "特效", "渲染"],
    "剧情": ["剧情", "故事", "文案", "编剧", "叙事"],
    "氪金": ["氪金", "付费", "充值", "月卡", "648", "抽卡"],
})

# 提取代表性评论
representatives = analyst.get_representative_comments(df_comments, topics, n=3)

# 每个视频的三连互动分析
for vi in all_video_infos:
    engagement = analyst.analyze_engagement(vi)
```

#### 单视频模式的分析

```python
analyst = BilibiliAnalyst()

# 加载数据
df_comments, df_danmaku = analyst.load_data(comments, danmakus)

# LDA主题分析（基于评论文本）
topics = analyst.run_lda(df_comments, language="auto", n_topics="auto")

# 弹幕密度峰值分析（B站独有能力）
danmaku_peaks = analyst.analyze_danmaku_density(
    df_danmaku,
    video_duration=video_info["duration"],  # 视频时长（秒）
    window_seconds=30,                       # 统计窗口（秒）
)

# 三连互动分析（B站独有能力）
engagement = analyst.analyze_engagement(video_info)

# 关键词声量统计
sov = analyst.share_of_voice(df_comments, df_danmaku, keywords={
    "画质": ["画质", "画面", "建模", "特效", "渲染"],
    "剧情": ["剧情", "故事", "文案", "编剧", "叙事"],
    "氪金": ["氪金", "付费", "充值", "月卡", "648", "抽卡"],
})

# 提取代表性评论和弹幕
representatives = analyst.get_representative_comments(df_comments, topics, n=3)
```

### Step 4：输出产出

**必须产出以下三项交付物**：

| 交付物 | 格式 | 说明 |
|--------|------|------|
| 源数据 | .xlsx | 全部评论+弹幕原文 + 点赞数 + 时间戳 + 主题标注 |
| 文字报告 | Markdown | 按用户报告风格输出结构化分析 |
| HTML报告 | .html | 用report-generator skill的暗色系模板（如可用） |

### ⚡ 语言规范（最高优先级）

> **核心规则：B站内容以中文为主，报告全部使用中文撰写。**

具体要求：

| 内容类型 | 语言处理方式 | 示例 |
|---------|------------|------|
| 报告正文 | **纯中文** | "该主题反映了玩家对抽卡机制的不满" |
| 主题名称 | **中文命名** | "主题一：版本更新与角色强度争议" |
| LDA 高频关键词 | **直接使用中文** | `抽卡`、`保底`、`强度`、`水军` |
| 真实评论/弹幕佐证 | **保留原文** | 见下方格式示范 |
| 表格标签/表头 | **中文** | "主题名称"、"提及次数"、"占比" |

**真实评论佐证的标准格式**：
```
💬 真实评论佐证：

> "说实话这个版本强度膨胀太严重了，老角色完全没法用，只能继续氪新卡"
> —— 用户昵称 | 👍 2,847 | 💬 156条回复 | 🕐 2026-02-15
```

**真实弹幕佐证的标准格式**：
```
🎯 弹幕高峰佐证（视频 02:34 处，密度峰值 47条/30秒）：

> "草" / "笑死" / "什么鬼" / "太强了" / "？？？"
> 分析：此处为角色大招释放画面，弹幕集中表达震撼与兴奋
```

### 报告结构

**话题搜索模式的报告结构（多视频汇总）**：
```
1. 元信息（搜索关键词、分析视频数量、总评论/弹幕数、采集时间）
   - 视频列表概览（标题、BV号、UP主、播放量、评论数）
2. 总览：该话题在B站的讨论热度判断
3. LDA主题聚类（基于汇总后的全部评论）
4. 各视频互动数据对比（播放-点赞比、三连率）
5. 关键词声量统计
6. 跨视频的弹幕词频对比
7. 总结与战略建议（P0/P1/P2）
```

**单视频模式的报告结构**：
```
1. 元信息（视频标题、BV号、UP主、播放量、三连数据、评论/弹幕总量、采集时间）
2. 总览：视频互动健康度评估（播放-点赞比、投币-收藏比等）
3. 第一部分：定性分析——LDA 主题聚类
   - 主题一：[中文主题名称]
     - 特征关键词
     - 分析解读
     - 💬 真实评论佐证（2-3条）：原文 + 点赞数 + 回复数 + 时间
   - 主题二：...
4. 第二部分：弹幕密度峰值分析（B站独有）
   - 弹幕时间线密度图描述
   - Top5密度峰值时间点 + 对应弹幕内容 + 视频画面推测
   - 关键发现：哪些画面引发最强情绪反应？
5. 第三部分：三连互动分析（B站独有）
   - 播放量 vs 点赞 vs 投币 vs 收藏 的比值分析
   - 与同类视频基准线的对比
   - 互动质量判断（"路过点赞" vs "真爱三连" vs "收藏吃灰"）
6. 第四部分：定量分析——关键词声量份额
7. 总结与战略建议（P0/P1/P2优先级）
```

### 质量要求
1. **主题数量**：必须通过困惑度 (Perplexity) 测算，不得硬编码
2. **真实佐证**：每个主题必须附带 2-3 条真实评论，包含点赞数和回复数
3. **排序规范**：主题按权重从高到低顺次编号
4. **数据透明**：报告中必须注明样本量、分析方法
5. **B站特有数据利用**：必须包含弹幕密度峰值分析和三连互动分析，这是B站相比其他平台的核心差异化价值
6. **结论来源**：所有结论必须基于真实数据，严禁编纂
7. **交付完整性**：必须同时提供 Excel 源数据 + 文字报告 + HTML 报告

## ⚔️ 战略分析层（v1.2 新增 — 最高优先级）

> **数据采集是基础，战略解读才是价值所在。** 纯LDA主题聚类只是"数据整理"，不是"分析"。
> 必须在LDA结果之上叠加以下战略分析维度，否则报告不合格。

### 1. 采样偏差声明（必须在报告开头标注）

每份报告必须明确指出数据的采样局限性：

```
⚠️ 采样偏差说明：
- 本次采集评论 X 条（占总评论 Y 条的 Z%），以热门/高赞评论为主
- 热门排序天然偏向正面声音（高赞=共识，而非全貌）
- 沉默的大多数（浏览但不评论的用户）未被覆盖
- 以下分析结论适用于"活跃发声群体"，不代表全体受众
```

### 2. 舆论风险预警矩阵

对每个LDA主题进行风险评估：

| 主题 | 当前声量 | 情绪倾向 | 扩散潜力 | 风险等级 | 建议 |
|------|---------|---------|---------|---------|------|
| 主题A | 高(30%) | 正面为主 | 低 | 🟢 安全 | 维持 |
| 主题B | 中(15%) | 负面上升 | 高（涉及公平性） | 🔴 高危 | 版本上线前需官方回应 |

**扩散潜力判断标准**：
- 涉及**公平性/pay-to-win** → 高扩散（玩家群体最敏感的红线）
- 涉及**技术问题/Bug** → 中扩散（可通过修复解决）
- 涉及**审美/剧情偏好** → 低扩散（主观分歧不易形成共识）
- 有**头部UP主/KOL**参与讨论 → 扩散力×3

### 3. 历史基线对比（有条件时必做）

如果用户分析的是系列视频（如同一游戏的多个PV），应尝试建立基线：

```
📈 与历史PV互动基线对比：
- 本次PV点赞率: 9.6% vs 上次PV: 7.2% → ↑33%（期待度上升）
- 本次PV投币率: 3.1% vs 上次PV: 2.8% → ↑11%（深度认可略升）
- 本次评论量: 3.2万 vs 上次: 4.1万 → ↓22%（需考虑发布时长差异）
```

### 4. 执行建议分级（P0/P1/P2）

报告结尾的建议必须按优先级分级，每条建议包含：
- **P0（立即行动）**：有明确风险或机会窗口，延迟=损失
- **P1（本周内）**：重要但不紧急，可纳入下个迭代
- **P2（持续观察）**：趋势信号，尚未形成定论

每条建议格式：
```
[P0] 具体建议内容
    依据：来自哪个数据/发现
    预期影响：做了会怎样/不做会怎样
```

### HTML 报告样式规范
- **配色**：白底黑字，简洁专业
- **字体**：系统默认无衬线字体
- **布局**：单栏居中，最大宽度 900px
- **元素**：
  - 关键词使用标签样式 (tag)
  - 引用评论使用引用框 (quote-box)，包含点赞数和回复数
  - 弹幕峰值用时间线/面积图可视化
  - 三连数据用雷达图或对比条形图
  - 重要洞察使用高亮框 (insight-box)

## 多视频对比模式

当用户提供多个BV号时，对每个视频独立采集分析，然后输出横向对比：
- 播放量与互动率对比
- 各视频Top主题对比
- 同一关键词在不同视频中的声量对比
- 弹幕情绪曲线对比

## B站数据的独特分析价值

相比其他平台，B站独有的数据优势：

| 字段 | 分析价值 |
|------|---------|
| 弹幕 (`danmaku`) | 实时情感反应流，密度峰值=情绪爆发点，B站独有数据 |
| 弹幕时间戳 (`progress`) | 精确到毫秒，可定位视频中引发最强反应的画面 |
| 投币数 (`coin`) | 比点赞更强的认可信号——需要消耗B币 |
| 收藏数 (`favorite`) | "值得回看"的判断，高收藏=长期价值认可 |
| 三连比例 | 点赞/投币/收藏的比值差异反映互动质量和用户意图 |
| 评论楼层 (`rpid`) | 评论热度排序，高赞评论=社区共识 |
| 评论回复数 (`rcount`) | 引发讨论的评论=争议或共鸣点 |
| UP主回复 (`up_action.reply`) | UP主是否回复=官方态度信号 |
| 评论标签 (`tag`) | 部分视频有"神评""热评"标签 |
| 视频分P (`cid`) | 长视频分P可按段分析弹幕情绪 |

## 常见游戏UP主/视频类型速查

| UP主类型 | 代表 | 分析价值 |
|---------|------|---------|
| 游戏官方号 | 原神/崩铁/鸣潮官方 | PV评论区=版本期待度晴雨表 |
| 头部评测UP | 老番茄/敖厂长/黑桐谷歌 | 评论区=泛玩家群体反馈 |
| 品类垂直UP | 各游戏专属UP主 | 评论区=核心玩家深度反馈 |
| 数据/攻略UP | 角色测评/配队攻略 | 评论区=硬核玩家理论讨论 |
| 吐槽/整活UP | 二创/鬼畜/吐槽向 | 弹幕=社区meme和情绪温度 |

## 注意事项

1. **无需API Key**：B站Web API大部分为公开接口，可直接调用
2. **速率限制**：无官方文档，实测建议每次请求间隔 0.5-1秒，避免触发风控
3. **弹幕接口**：新版弹幕接口使用protobuf编码（`dm/v1/seg.so`），脚本已内置解码逻辑
4. **评论分页**：评论接口每页最多20条，需逐页翻取；总评论数可能与实际可拉取数量不一致（被折叠/删除）
5. **Cookie可选**：不登录可获取大部分数据，登录态Cookie可获取更多折叠评论和会员弹幕
6. **视频下架**：部分视频可能被下架或限制访问，脚本会自动跳过并报告
7. **结论来源**：所有结论必须基于真实数据，严禁编纂
8. **交付完整性**：必须同时提供 Excel 源数据 + 文字报告 + HTML 报告

## 🔄 版本历史

- **v1.3** (2026-03-04): 移除Gacha转化漏斗（关键词分类法误判率高且仅适用gacha品类），战略分析层精简为通用框架
- **v1.2** (2026-03-04): 新增「战略分析层」——采样偏差声明、舆论风险预警矩阵、历史基线对比、P0/P1/P2执行建议分级。数据采集→战略解读的完整闭环
- **v1.1** (2026-03-04): 新增关键词搜索能力（`search_videos` + `search_and_collect`），支持话题分析模式，无需指定视频即可广泛采集分析
- **v1.0** (2026-03-04): 初始版本，完整的评论+弹幕采集+LDA分析+弹幕密度峰值+三连互动分析+声量统计功能
