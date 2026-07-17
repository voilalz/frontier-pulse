# 智域前沿 / Frontier Pulse

面向全球科技、AI、航空航天、军事动态、局部冲突、前沿技术与无人系统的自动日报。Cloudflare 托管静态网站，GitHub Actions 每天 `Asia/Tokyo 08:00` 抓取最近 24 小时的公开新闻、筛选 Top 10、生成中文编辑稿、维护归档、Atom 订阅，并可发送管理员邮件摘要。

仓库：<https://github.com/voilalz/frontier-pulse>
当前站点：<https://frontier-pulse.jiumi674.workers.dev>

## 已实现功能

- AI 中文标题、摘要、2–3 条关键事实和“为什么重要”；没有 API Key 时保留证据型规则摘要，不编造翻译。
- RSS/Atom + GDELT 并行采集，24 小时时间窗、链接清洗、同事件去重和来源合并。
- Reuters/AP 等通稿转载会按证据网络折算，不会因多个转载域名虚增“独立来源”；无效日期按时间窗边缘处理并降权。
- 每日 Top 10、多主题与来源限额，过滤 Sponsored / Advertorial 等商业样稿。
- 展示一个事件的全部来源、独立来源数量、来源置信度和可展开的评分分项。
- 按日归档、日期前后切换，以及按月分片的轻量跨日期搜索；完整评分与来源在展开时按需读取当期归档。
- 独立收藏页和关注词情报流；数据只保存在当前浏览器 `localStorage`。
- 懒加载新闻缩略图、单条永久锚点与复制链接、OG/Twitter 分享卡片、本地时区标识、搜索高亮和跨日期分组。
- 自动/手动深色主题和 Service Worker 离线回退；常规请求复用 ETag/CDN 缓存，仅手动刷新绕过缓存。
- 公开 `feed.xml` Atom 订阅，不需要收集访客邮箱。
- 生产环境不含硬编码样例。远程读取失败时，只能使用明确标警的“上次成功真实缓存”；没有缓存则展示空状态。
- `status.json` 记录最后尝试、最后成功与失败原因；页面对更新失败、超过 36 小时和条目不足 10 条发出醒目警告。
- GitHub Actions 成功生成日报后，可通过 SMTP 向管理员维护的收件人列表发送 HTML + 纯文本 Top 10 邮件。

## 数据链路

1. 并行读取配置中的公开 RSS/Atom 与 GDELT。
2. 清洗元数据，将同一事件的独立来源合并到 `sources[]`。
3. 按来源、时效、主题、影响信号、证据完整度和多源印证进行规则评分。
4. 配置 `OPENAI_API_KEY` 时，调用 OpenAI Responses API 完成中文编辑和 Top 10 复核；网络/结构化输出允许一次退避重试，结果仍须通过类别与来源多样性校验。
5. 校验恰好 10 条后，写入最新一期、按日归档、月度搜索分片、Atom Feed 和成功状态。
6. 失败时不覆盖 `news.json`，只写入失败状态；网页继续显示上一期真实数据并告警。
7. GitHub Actions 提交数据，Cloudflare 自动发布；配置 SMTP 时再发送邮件。

## 目录

```text
public/
  index.html                         网站入口
  assets/app.js                     今日/历史/收藏/关注视图与告警逻辑
  assets/styles.css                 响应式样式
  sw.js                             离线 App Shell 与数据网络优先缓存
  feed.xml                          Atom 订阅
  og-card.png                       分享卡片
  data/news.json                    最新一期 Top 10
  data/status.json                  更新健康状态
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

## 启用 AI 中文编辑

在 GitHub 仓库进入 `Settings → Secrets and variables → Actions`：

- Secret `OPENAI_API_KEY`：必需；不应写入源码。
- Variable `OPENAI_MODEL`：可选，默认 `gpt-5.6-luna`。

手动运行 `Actions → Daily news update → Run workflow`。成功后 `public/data/news.json` 应显示 `method: openai`，且每条包含 `title`（中文编辑标题）、`originalTitle`、`summary` 和 `keyFacts`。若 AI 调用、解析或多样性校验失败，系统使用规则版并把原因写入 `status.json.warnings`；页面会显示“规则回退”，而不是只在 Actions 日志中留痕。

## 缓存、搜索与订阅

- 常规页面加载使用不带时间戳的干净 URL，让浏览器、Cloudflare、ETag 和 `_headers` 中的 `max-age` 生效。
- 只有点击页面刷新按钮时才追加 `t=...` 并使用 `cache: no-store`。
- `search-index.json` 只列出月度分片；分片不保存 `scoreComponents`、`scoreReasons`、`confidenceReason` 等详情字段。用户展开搜索结果时再读取 `YYYY-MM-DD.json`。
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
