# 智域前沿 / Frontier Pulse

面向全球科技、AI、航空航天、军事动态、局部冲突、前沿技术、无人系统与前沿研究的情报聚合平台。Cloudflare 托管静态网站；GitHub Actions 每 3 小时更新 24 小时全量动态，每天 `Asia/Tokyo 08:00` 生成 Top 10 中文简报、论文雷达、历史归档、Atom 订阅，并可发送管理员邮件摘要。

仓库：<https://github.com/voilalz/frontier-pulse>
当前站点：<https://frontier-pulse.jiumi674.workers.dev>

## 已实现功能

- DeepSeek V4 Flash 或 OpenAI 可生成中文标题、摘要、2–3 条关键事实和“为什么重要”；没有 API Key 时保留证据型规则摘要，不伪装为已翻译。
- 18 个国际 RSS/Atom 信源 + GDELT 并行采集，覆盖官方机构、航空航天、AI、科技、军情与全球冲突媒体，并执行 24 小时时间窗、链接清洗、同事件去重和来源合并。
- Reuters/AP 等通稿转载会按证据网络折算，不会因多个转载域名虚增“独立来源”；无效日期按时间窗边缘处理并降权。
- 每日 Top 10、多主题与来源限额，过滤 Sponsored / Advertorial 等商业样稿。
- 独立“全量动态”视图保留最多 300 条通过时间窗、相关性、去重与商业内容过滤的候选，可按 6/12/24 小时、来源、主题和关键词筛选；每日 Top 10 在流中明确标记。
- 独立“论文雷达”读取 arXiv 官方 Atom API，覆盖 AI、机器学习、机器人、无人与控制系统、空间科学、量子和先进材料；除分类采集外，系统采集词会直接查询论文标题和摘要。
- “我的论文关键词”可在浏览器保存最多 20 个中英文词，自动筛选、命中高亮并生成专属论文流；个人词不上传，系统实际采集词则公开显示在页面上。
- 配置 DeepSeek 时，论文雷达可分批为最多 60 篇生成中文标题、摘要、研究问题、方法、主要发现与局限；全量动态最多翻译 120 条，并复用未变化条目的既有翻译以控制成本。单个批次失败不会删除原始内容。
- 首页重构为“今日必读 Top 3 → 执行摘要 → 完整 Top 10”，减少首屏信息拥挤，同时保留全部证据详情。
- 展示一个事件的全部来源、独立来源数量、来源置信度和可展开的评分分项。
- 按日归档、日期前后切换，以及按月分片的轻量跨日期搜索；完整评分与来源在展开时按需读取当期归档。
- 独立收藏页和关注词情报流；数据只保存在当前浏览器 `localStorage`。
- 懒加载新闻缩略图、单条永久锚点与复制链接、OG/Twitter 分享卡片、本地时区标识、搜索高亮和跨日期分组。
- 自动/手动深色主题和 Service Worker 离线回退；常规请求复用 ETag/CDN 缓存，仅手动刷新绕过缓存。
- 公开 `feed.xml` Atom 订阅，不需要收集访客邮箱。
- 生产环境不含硬编码样例。远程读取失败时，只能使用明确标警的“上次成功真实缓存”；没有缓存则展示空状态。
- `status.json` 记录最后尝试、最后成功与失败原因；页面对更新失败、超过 36 小时和条目不足 10 条发出醒目警告。
- 日报候选不足时先复用不超过 8 小时的已验证动态缓存，再按 36/48/72 小时逐级补充；超过 24 小时的条目会降权并标注“补充观察”。候选分布过度集中时才分级放宽主题/来源配额，页面与状态文件都会公开说明。
- GitHub Actions 成功生成日报后，可通过 SMTP 向管理员维护的收件人列表发送 HTML + 纯文本 Top 10 邮件。

## 数据链路

1. 并行读取配置中的公开 RSS/Atom 与 GDELT，清洗元数据，将同一事件的独立来源合并到 `sources[]`。
2. 按来源、时效、主题、影响信号、证据完整度和多源印证进行规则评分，并把全部合格候选写入 `stream.json`。
3. 若 24 小时合格候选不足 10 条，先合并最近一次已验证的三小时动态缓存，再按 36/48/72 小时逐级补充并施加时效降权；若只是候选分布过度集中，则分级放宽主题/来源配额，而不是让整期刷新失败。
4. 配置 `DEEPSEEK_API_KEY` 时，调用 DeepSeek Chat Completions（JSON 输出、关闭思考模式）完成 Top 10 中文编辑，并分批翻译动态流；也保留 OpenAI Responses 作为可选后备。网络/结构化输出允许一次退避重试，选稿结果仍须通过类别与来源多样性校验。
5. 独立按 arXiv 分类与 `research.collection_keywords` 查询标题/摘要，合并去重后按主题相关性、摘要完整度与新鲜度排序；可选 AI 中文编辑不会改变原始论文元数据。
6. 校验日报恰好 10 条后，写入最新一期、按日归档、月度搜索分片、Atom Feed 和健康状态；全量动态保持严格 24 小时语义，允许低流量日少于 10 条。
7. 只有在 72 小时内仍无法找到 10 条可验证候选，或完全没有 24 小时候选时，才保留上一版真实日报并记录失败，绝不生成虚构新闻。
8. GitHub Actions 提交数据，Cloudflare 自动发布；配置 SMTP 时再发送邮件。

## 目录

```text
public/
  index.html                         网站入口
  assets/app.js                     今日/动态/论文/历史/收藏/关注视图与告警逻辑
  assets/styles.css                 响应式样式
  sw.js                             离线 App Shell 与数据网络优先缓存
  feed.xml                          Atom 订阅
  og-card.png                       分享卡片
  data/news.json                    最新一期 Top 10
  data/status.json                  更新健康状态
  data/stream.json                  最近 24 小时合格动态流（最多 300 条）
  data/stream-status.json           动态流健康状态
  data/research.json                最近 7 天前沿论文雷达
  data/archive/YYYY-MM-DD.json      完整每日版
  data/archive/index.json           可用日期与期刊元数据
  data/archive/search-index.json    月度搜索分片清单
  data/archive/search-YYYY-MM.json  仅含可检索字段的月度分片
scripts/update_news.py              采集、去重、评分、AI 编辑、归档与状态
scripts/send_digest.py              SMTP 邮件摘要
scripts/check_production.py         线上安全头与缓存头验收
config/news_config.json             主题、信源、权重、时区、模型和归档期限
tests/                              完全离线测试与固定样例
.github/workflows/daily-news.yml     每天 08:00 更新、提交与发信
.github/workflows/stream-update.yml  每 3 小时更新全量动态流
```

## 本地运行

只依赖 Python 3.11+ 标准库；前端不需要构建工具。

```bash
python -m unittest discover -s tests -v
node --check public/assets/app.js
node --check public/sw.js

python scripts/update_news.py \
  --fixture tests/fixtures/articles.json \
  --output /tmp/frontier-news.json \
  --archive-dir /tmp/frontier-archive \
  --archive-index /tmp/frontier-archive/index.json \
  --search-index /tmp/frontier-archive/search-index.json \
  --status-output /tmp/frontier-status.json \
  --stream-output /tmp/frontier-stream.json \
  --stream-status-output /tmp/frontier-stream-status.json \
  --research-output /tmp/frontier-research.json \
  --research-fixture tests/fixtures/papers.json \
  --feed-output /tmp/frontier-feed.xml \
  --skip-ai \
  --now 2026-07-16T00:00:00Z

python scripts/send_digest.py --input /tmp/frontier-news.json --dry-run
python -m http.server 8000 --directory public
```

浏览器访问 `http://localhost:8000`。实时采集使用：

```bash
python scripts/update_news.py
```

## 启用 DeepSeek V4 Flash 中文翻译

在 GitHub 仓库进入 `Settings → Secrets and variables → Actions`：

- 在 **Secrets** 页添加 `DEEPSEEK_API_KEY`。值只粘贴到 GitHub 的加密输入框，不要发到聊天、Issue、代码或 Cloudflare 前端变量。
- 在 **Variables** 页添加 `AI_PROVIDER=deepseek`。
- 在 **Variables** 页添加 `DEEPSEEK_MODEL=deepseek-v4-flash`。仓库默认值相同，但显式配置便于审计。

然后依次手动运行：

1. `Actions → Daily news update → Run workflow`，生成 Top 10 和论文中文编辑。
2. `Actions → Full stream update → Run workflow`，补齐全量动态中文翻译。
3. 等待 Cloudflare 发布最新 `main`，在网页中确认卡片出现“DeepSeek 中文”。

成功后可检查：

- `public/data/news.json`：`method: deepseek`、`editorialModel: deepseek-v4-flash`，条目含中文 `title`、`summary` 与 `keyFacts`。
- `public/data/research.json`：`editorialProvider: deepseek`、`translatedItemCount > 0`。
- `public/data/stream.json`：`translationProvider: deepseek`、`translatedItemCount > 0`。
- `public/data/status.json` 和 `stream-status.json`：记录模型、翻译数量及公开的批次警告，但绝不包含密钥。

本地运行可复制 `.env.example` 中的变量到当前终端环境，再执行 `python scripts/update_news.py`。不要提交真实 `.env`。系统使用官方兼容地址 `https://api.deepseek.com/chat/completions`；模型与 JSON 输出参数以 [DeepSeek 官方 API 文档](https://api-docs.deepseek.com/) 为准。

若 DeepSeek 调用、解析或多样性校验失败，Top 10 自动回退规则版；论文与动态只保留成功批次，并显示翻译不完整警告。原始标题、摘要和链接不会因翻译失败而丢失。`AI_PROVIDER=auto` 时优先选择已配置的 DeepSeek；仅在没有 DeepSeek 密钥时选择 OpenAI，不会在一次失败调用中跨供应商自动重试。若要继续使用 OpenAI，则设置 `AI_PROVIDER=openai`、Secret `OPENAI_API_KEY` 和 Variable `OPENAI_MODEL`。

## 论文关键词：个人筛选与服务器采集

这是两个不同层级，避免用户误以为本机输入会改变所有人的采集任务：

- **我的论文关键词**：在“论文雷达”页面逐个添加，最多 20 个。只写入当前浏览器 `localStorage`，立即筛选现有论文、突出命中位置并生成“我的论文流”。若中文词没有命中英文原文，可再添加对应英文术语。
- **系统采集词**：由管理员修改 `config/news_config.json` 的 `research.collection_keywords`。每日任务会用 `ti:` 与 `abs:` 搜索 arXiv 标题和摘要，因此能发现不在既有分类候选中的特定方向。它是全站共享配置，修改后需要重新运行日报。

一个采集词的配置示例：

```json
{
  "label": "多模态智能体",
  "query": "multimodal agent",
  "aliases": ["multimodal agents", "multimodal AI agent", "多模态智能体"],
  "priority": 10
}
```

`label` 用于中文展示，`query` 与最多若干 `aliases` 组成 arXiv 标题/摘要查询，`priority` 影响研究相关度。最多读取前 20 个有效定义；建议优先使用英文专业术语，并把中文作为标签或匹配别名。arXiv 查询字段语法和限速要求见 [arXiv API User's Manual](https://info.arxiv.org/help/api/user-manual.html)。

## 缓存、搜索与订阅

- 常规页面加载使用不带时间戳的干净 URL，让浏览器、Cloudflare、ETag 和 `_headers` 中的 `max-age` 生效。
- 只有点击页面刷新按钮时才追加 `t=...` 并使用 `cache: no-store`。
- `search-index.json` 只列出月度分片；分片不保存 `scoreComponents`、`scoreReasons`、`confidenceReason` 等详情字段。用户展开搜索结果时再读取 `YYYY-MM-DD.json`。
- `stream.json` 缓存 5 分钟并由三小时工作流更新；`research.json` 缓存 30 分钟并由每日工作流更新。两者都采用分页渲染，避免一次创建数百个 DOM 节点。
- 论文查询按研究方向合并分类，并为每个系统采集词查询标题与摘要；所有查询单连接顺序执行，请求间等待 3.1 秒，同一批任务每天运行一次，符合 [arXiv API 限速与缓存建议](https://info.arxiv.org/help/api/tou.html)。
- 阅读器订阅地址为 `/feed.xml`。这是匿名、无邮箱收集的公开 Atom Feed；管理员 SMTP 邮件仍是另一条独立通道。
- `.github/workflows/production-smoke.yml` 每日检查线上 CSP、`nosniff`、ETag/缓存头与 Feed。也可本地运行：

```bash
python scripts/check_production.py --site-url https://frontier-pulse.jiumi674.workers.dev/
```

## 启用邮件推送

本项目采用“管理员维护收件人”的静态安全方案，不在公开网页收集邮箱。多个收件人通过密送发送，彼此不可见。

在 GitHub Actions Secrets 中添加：

- `SMTP_HOST`
- `SMTP_USERNAME`（SMTP 服务允许匿名时可留空）
- `SMTP_PASSWORD`（通常是 SMTP 授权码）
- `EMAIL_FROM`
- `EMAIL_TO`（多个地址用逗号或分号分隔）
- `EMAIL_REPLY_TO`（可选）

在 Actions Variables 中添加：

- `SMTP_PORT`：默认 `587`
- `SMTP_USE_SSL`：端口 465 时设为 `true`
- `SMTP_STARTTLS`：端口 587 通常设为 `true`
- `SITE_URL`：例如 `https://frontier-pulse.jiumi674.workers.dev`

未配置 `SMTP_HOST`、`EMAIL_FROM` 或 `EMAIL_TO` 时，脚本会显示 `Email push not configured; skipping` 并安全跳过，不影响网站更新。建议先在本地或 Actions 使用 `--dry-run` 验证模板，再手动运行一次日报工作流验证真实投递。

## 最简上线方式

1. GitHub `Settings → Actions → General → Workflow permissions` 选择 `Read and write permissions`。
2. Cloudflare Dashboard 进入 `Workers & Pages → Create → Pages → Connect to Git`，连接本仓库。
3. Production branch 设为 `main`，Framework preset 设为 `None`，Build command 留空，Build output directory 设为 `public`。
4. 手动运行一次 `Daily news update`，确认生成 10 条、归档和 `status.json`。
5. 在 Cloudflare 部署页面确认最新 `main` 已发布，再按需绑定自有域名。

完整配置和故障排查见 [DEPLOY_CLOUDFLARE.md](DEPLOY_CLOUDFLARE.md)。

## 调整主题与存储期限

- 分类、关键词、信源和权重：`config/news_config.json`
- 采集窗口：`lookback_hours`，默认 24
- 全量流上限：`stream_limit`，默认 300
- 低流量恢复：`daily_recovery.stream_cache_max_age_hours` 与 `daily_recovery.backfill_windows_hours`
- 论文窗口、上限、研究方向与采集词：`research.lookback_days`、`research.limit`、`research.arxiv_categories`、`research.collection_keywords`
- 每日条数：`top_n`，当前前端和校验固定为 10
- 搜索索引保留期：`archive_retention_days`，默认 730 期
- 前端过期阈值：`public/assets/app.js` 中的 36 小时判断

每日工作流使用浅克隆，搜索数据按月分片并只保存可检索字段，降低 Git checkout 和浏览器解析成本。完整归档仍会随 Git 历史增长；运行多年后应把旧归档迁移到 R2 或独立数据分支，但先保留 `index.json`、搜索清单和日期详情 URL 的兼容层。

## 数据、版权与安全边界

- 只保存标题、短摘要、关键事实、来源元数据和原文链接，不镜像新闻全文。
- AI 只能依据候选标题、RSS 描述、来源和时间生成编辑稿，提示词禁止补写无证据事实。
- “重要度”是编辑排序分，“置信度”是来源证据提示，均不代表事实真伪概率。
- 军事与冲突内容使用中性表述；关键结论应回到一手文件并进行跨来源核验。
- API Key、SMTP 密码和收件人只能放在 GitHub Secrets 或本地环境变量中。
