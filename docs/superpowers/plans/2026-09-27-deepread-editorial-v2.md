# 每日深读编辑内容模型 v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将最多 12 件候选压缩成 4～6 件有历史变化线索的正文，并提供跨 Web/公众号/邮件的编辑 JSON。

**Architecture:** 保留 `daily_deepread.py` 的候选筛选与历史 v1 逻辑；`deepread_editorial.py` 执行 v2 提纲、成文和契约校验，`update_news.py` 接入事件库；`app.js` 为 v2 提供 Web 适配并兼容 v1；工作流修订号触发当日重生。

**Tech Stack:** Python 3.11 标准库、原有结构化模型适配器、静态 JavaScript/CSS、unittest。

**Spec:** `docs/superpowers/specs/2026-09-27-deepread-editorial-v2-design.md`

## Global Constraints

- 严格滚动 24 小时内、最多 12 件候选；正文 4～6 件，素材不足按实际数量。
- 历史只允许同一 canonical `eventId`、早于当期的记录；新闻来源、图片和 ID 由程序控制。
- 新版输出 `schemaVersion: 2`；旧版归档继续兼容；前端遵守中国主体过滤。
- 证据标签不等于事实核验；稿件内容不镜像原始全文。

## Review Focus

- 被移除的中国主体事件不得通过导语、章节或段落残留。
- 恶意模型输出的 URL、事件 ID、HTML 不得进入公开 JSON。
- 相同 URL 的多个转载不算多源；跨事件历史关联不算同事件进展。
- 抓取仅有 0～3 个候选时不得造满 4 个或写完整性成功状态。
- 同日旧版升级与历史日期 v1 归档必须各自正常打开。

### Task 1: 提纲选择与历史证据

**Files:** `scripts/deepread_editorial.py`, `scripts/update_news.py`, `config/news_config.json`, `tests/test_deepread_editorial.py`, `tests/test_update_news.py`

**Interfaces:** `build_daily_deepread(items, config, now, runtime=None, request_json=None, *, event_registry=None, history_items=None) -> dict`；程序从事件库和既有搜索归档抽取可核对的同 ID 时间线。

- [x] 先写失败测试：12 候选选 4～6 件、无关事件拆节、历史同 ID 与旧日期限定、4 种证据标签。
- [x] 运行 `python -m unittest discover -s tests -p 'test_deepread_editorial.py' -q`，确认缺失行为而失败。
- [x] 实现提纲生成/校验、程序兜底选择和事件库接入。
- [x] 运行同一测试，确认通过。

### Task 2: 编辑成文与 v2 契约

**Files:** `scripts/deepread_editorial.py`, `tests/test_deepread_editorial.py`, `tests/test_update_news.py`, `.github/workflows/daily-news.yml`

**Interfaces:** `chapters[].blocks[]` 引用 `events[].newsId`，`type=change` 只能引用有历史的事件。

- [x] 先写失败测试：提纲和写作分两次请求；变化段引用历史；无效响应降级；输出无 `summary + analysis + watchFor` 模板。
- [x] 运行目标测试，确认行为失败。
- [x] 实现写作 schema、验证、短稿降级；修订号升级并调整流水线断言。
- [x] 运行目标测试，确认通过。

### Task 3: Web v2 展示与 v1 兼容

**Files:** `public/assets/app.js`, `public/assets/styles.css`, `tests/test_deepread_frontend.py`

**Interfaces:** `normalizeDeepread` 分派 v1/v2；`renderDeepreadArticle` 分派 v1/v2，标签依据白名单显示。

- [x] 先写失败测试：v2 段落和四级证据、旧 v1、过滤后跨事件文字清空与恶意 URL 拒绝。
- [x] 运行 `python -m unittest discover -s tests -p 'test_deepread_frontend.py' -q`，确认缺失行为而失败。
- [x] 实现 v2 标准化和 Web 渲染，完善响应式章节样式。
- [x] 运行目标测试，确认通过。

### Task 4: 全链路验证与迁移说明

**Files:** `README.md`, `docs/deepread-editorial-contract.md`

- [x] 用隔离 fixture 运行日报，检查 v2 JSON、当日归档与索引。
- [x] 运行 `python -m unittest discover -s tests -q`、`node --check public/assets/app.js`、`node --check public/sw.js`。
- [x] 检查 PR 变更与生成样本，记录旧版归档兼容和剩余内容核验限制。
