# 每日深读审查修订 Implementation Plan

> For agentic workers: execute inline with superpowers:executing-plans; preserve this independent branch.

**Goal:** 修复整期失败和短译文退化，形成可逐主题发布的中文解读。
**Architecture:** revision 13 的主题生成与事实校对模块；保留旧版本解析用于历史归档。复用证据捕获、日报发布事务和独立恢复入口。
**Tech Stack:** Python 标准库、原生 JavaScript/CSS、GitHub Actions。
**Spec:** docs/superpowers/specs/2026-10-08-deepread-review-design.md

## Global Constraints

- 1–3 主题，主篇 800–1500 字，短篇 300–500 字；合格简版主题至少 300 字。
- 事实逐句 1–3 个 evidenceId；独立校对只接受 supported。
- 不合并、不部署，不改写生产数据；保留 08:00 更新。
- 沿用旧稿最多 1 天；修复最多 1 次；合格主题不重复生成。

## Review Focus

- 模型校对缺项或异常必须失败关闭，不能放过新事实。
- 同公司不同金额/行动不能误聚类；同额转载须合并。
- 旧 eventId 无正文历史时不能补造背景。
- 仅一篇合格或全部失败时页面仍说明当日状态。
- 发布事务不能强迫新模型再次满足旧 4–6 新闻及观察数量。

### Task 1: 证据与发布止血

Files: scripts/evidence_trace.py, scripts/deepread_quality.py, tests/test_deepread_topics.py
Interfaces: split evidence sentences; choose_readable_deepread(draft, previous, publication_date); revision 13 dispatch to topic validators.

- [x] 先写缩写断句、限定词、一天沿用及不同 eventId 重复的失败回归，运行确认失败。
- [x] 实现缩写保护、限定词同义、逐主题发布与有期限沿用。
- [x] 用新主题验证器校核事实/分析及诊断，运行必要回归。

### Task 2: 主题生成和独立校对

Files: scripts/deepread_topics.py, scripts/deepread_topic_quality.py, scripts/deepread_editorial.py, scripts/recover_deepread.py, scripts/update_news.py, scripts/publication.py
Interfaces: build_daily_deepread(..., existing_article=None) -> revision 13; validate_topic_article(article, complete=False); per-sentence checks with immutable text/evidence bindings.

- [x] 写有一个失败主题的生成/发布回归，确认旧生成器不能独立发表。
- [x] 实现去重、编辑过滤、平衡候选、项目历史、主题提纲、逐章写作及独立校对。
- [x] 反馈具体失败句后仅重写该章一次；复用当日已完成章节；接通发布契约与恢复调度。
- [x] 冻结 10/8 材料离线回放，记录真实材料覆盖与验证限制。

### Task 3: 阅读与交付

Files: public/assets/app.js, public/assets/styles.css, docs/deepread-editorial-contract.md, .github/workflows/deepread-recovery.yml, tests/test_deepread_topics.py
Interfaces: revision 13 topic normalization, concise footnotes, partial/brief/retained reader states.

- [x] 验证新格式能呈现事实和分析、部分发布，旧日期按旧版可读。
- [x] 实现句末引用、统一原文、单主图和当前日期提示。
- [x] 必要离线测试、JS 语法/客户端验证、截图检查；记录通过结果及未做的真实模型/线上验收。
- [x] 提交并保存独立远程分支，交付修改说明；不合并、不部署。
