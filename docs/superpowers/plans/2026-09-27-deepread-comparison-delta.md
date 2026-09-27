# 每日深读比较与变化优先 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让五条核心报道在确有共同问题时形成比较章节，并优先选择有实质变化、较强证据的报道，清理图片说明与政治政策内容，输出可信的短观察。

**Architecture:** `news_evidence.py` 清除新抓取的图片说明；新的 `deepread_editorial_signals.py` 集中深读专用过滤、缓存材料清理、比较议题和变化评分；`deepread_editorial.py` 控制候选优先级、提纲/成文校验与编辑模型，`app.js` 兼容新版附加字段及旧归档。

**Tech Stack:** Python 3.12 标准库、现有结构化模型适配器、静态 JavaScript/CSS、unittest。

**Spec:** `docs/superpowers/specs/2026-09-27-deepread-comparison-delta-design.md`

## Global Constraints

- 保持 24 小时/最多 12 条候选和 4～6 条核心正文，默认 5 条，`schemaVersion: 2`，`generationRevision: 7`。
- 比较仅限 2～3 条不同事件、共享具体 `comparisonKey`；固定说明“并列比较不代表事件之间存在因果关系。”
- `deltaScore` 仅由可核验同 ID 历史的实质行动阶段变化产生，取 0、2、3；来源加分不得覆盖明显更重要的报道。
- “今日观察”仅在完整校验后给出 2～3 条、各 20～80 字及对应事件的准确证据片段；失败不伪造。
- 政治政策排除仅作用于新生成的深读内容；其他新闻栏目与旧归档数据不变。本任务不合并、不上线。

## Review Focus

- 图片说明与摄影署名从受限文章的 RSS 退路进入深读：新证据和旧缓存摘要都应被清理。
- “影像发现异常目标”本身是报道事实时，不能因为“影像”二字误删。
- 误分类在“军事动态”的白宫媒体准入报道必须被过滤；技术装备报道提到国防部或议会时保留。
- 仅有同 ID 转载或无真实阶段变化时 `deltaScore=0`；不同事件不得借比较段冒充相互作用。
- 前端过滤事件后，旧标题、导语、观察或比较文字不得引用已删事件；v1/v2 归档保持可读。

### Task 1: 政治过滤与图片说明根因

**Files:** 新建 `scripts/deepread_editorial_signals.py`；修改 `scripts/news_evidence.py`、`scripts/deepread_editorial.py`；测试 `tests/test_news_evidence.py`、`tests/test_deepread_editorial.py`。

**Interfaces:** `is_political_policy(item: dict) -> bool`；`strip_caption_text(value: str) -> str`，适用于原摘要与证据文本。

- [ ] 写失败测试：含 `Space Force photo by Gwen Kurzen` 的 RSS 段与“报道配图显示……照片由……拍摄”不进正文；HTML `<figure>` 排除，真正的卫星影像事实保留。
- [ ] 写失败测试：白宫排除 CNN 报道、选举及政策法案排除；国防部技术试验及护卫舰项目保留；禁入文字不进入提纲输入。
- [ ] 运行两个目标测试文件，核对预期 RED。
- [ ] 最小实现证据提取与深读输入处理，运行目标测试至 GREEN，检查不会修改新闻流已存档内容。

### Task 2: DeltaScore 与证据优先级

**Files:** `scripts/deepread_editorial_signals.py`、`scripts/deepread_editorial.py`、`tests/test_deepread_editorial.py`。

**Interfaces:** `delta_score(current: dict, history: list[dict]) -> int`；`editorial_priority(item: dict) -> tuple`；正文事件目录增加 `deltaScore`。

- [ ] 写失败测试：同 ID“计划→完成”=2、“计划→取消”=3、同标题转载/跨 ID/旧 metadata 不可核对=0；同等重要度下高 Delta 与一手/多源入选，明显更高重要度的单源不被挤掉。
- [ ] 运行目标测试核对 RED。
- [ ] 计算历史与证据等级后在 12 条素材池内进行确定性核心选择；提纲请求限制在已选成员，保留章节发现；测试 GREEN。

### Task 3: 可核对的比较章节

**Files:** `scripts/deepread_editorial_signals.py`、`scripts/deepread_editorial.py`、`tests/test_deepread_editorial.py`。

**Interfaces:** `comparison_keys(item: dict) -> set[str]`；章节 `kind`, `comparisonKey`, `comparisonNote`；正文 `blocks[].type="comparison"`。

- [ ] 写失败测试：不同事件跨类别但共享“AI 智能体”可以组成一个 2～3 件比较章节；仅共享政府/科技/大类词的提纲被拆节；比较段必须引用所有成员且不得声称事件因果。
- [ ] 运行目标测试核对 RED。
- [ ] 使提纲与写作 schema 接受并校验比较章；固定非因果说明、失败降级和前端兼容字段；测试 GREEN。

### Task 4: 极短观察、Web 与端到端

**Files:** `scripts/deepread_editorial.py`、`public/assets/app.js`、`public/assets/styles.css`、`tests/test_deepread_editorial.py`、`tests/test_deepread_frontend.py`、`.github/workflows/daily-news.yml`、`docs/deepread-editorial-contract.md`、`README.md`。

**Interfaces:** `observations[]` 每项 `{text, newsIds, supports:[{newsId,supportQuote}]}`；v2 Web 适配后显示“今日观察”，旧版缺字段照常读取。

- [ ] 写失败测试：两条有准确摘录的判断被保留；无匹配摘录、无效 ID、引用全部核心事件的泛化总结被拒；前端过滤时清除观察与比较段；旧归档仍渲染。
- [ ] 运行目标测试核对 RED，最小实现观察校验与页面显示，目标测试 GREEN。
- [ ] 将修订号 7 写入工作流与契约；运行全部 unittest、Node 语法检查、配置检查与离线 2026-09-27 样本回放。
- [ ] 核对 PR 范围、CI 与 `main` 差异；仅推送隔离分支并开待审查 PR，不合并、不运行线上发布。
