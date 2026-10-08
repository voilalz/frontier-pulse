# Cloudflare Workers 部署与上线清单

正式域名为 `https://newsfrontier.top/`，由 Cloudflare Worker `frontier-pulse` 提供（仅静态资源，没有 Worker 脚本）。部署只有一条路径：

1. GitHub Actions 按计划生成数据，并提交到 `main`；
2. Cloudflare Workers Builds 监听 `main`，执行 `npx wrangler deploy`；
3. Wrangler 读取仓库根目录的 `wrangler.jsonc`，把 `public/` 上传为静态资源。

`public/_headers` 提供安全头与缓存头；`public/.assetsignore` 中列出的文件只留在仓库里，不会上传（目前是前端从不读取、单个超过 6 MB 的 `events.json`）。

旧的 Cloudflare Pages Direct Upload 工作流（`pages-deployment.yml`）一直处于停用状态，已删除。

## 1. 开启 GitHub Actions 写权限

打开 <https://github.com/voilalz/frontier-pulse/settings/actions>：

1. 找到 `Workflow permissions`。
2. 选择 `Read and write permissions`。
3. 保存。

如 `main` 启用了分支保护，需要允许 `github-actions[bot]` 提交 `public/data` 与 `public/releases`。

## 2. Cloudflare Workers Builds 设置

在 Cloudflare Dashboard 打开 `Workers & Pages → frontier-pulse → Settings → Build`，应为：

- Git 仓库：`voilalz/frontier-pulse`，生产分支 `main`；
- Build command：留空；
- Deploy command：`npx wrangler deploy`；
- Root directory：仓库根目录。

Worker 名称、资源目录和兼容日期都写在 `wrangler.jsonc`，修改部署设置请改这个文件，不要只改 Dashboard。自定义域名 `newsfrontier.top` 在 Dashboard 的 `Settings → Domains & Routes` 中维护；`wrangler.jsonc` 不声明 `routes`，部署不会改动已绑定的域名。

## 3. 运行一次日报

进入仓库 `Actions → Daily news update → Run workflow`。成功标准：

- 工作流绿色通过；
- `public/data/news.json` 包含 `timezone: Asia/Shanghai`，`items` 恰好为 10 条；
- Cloudflare Worker 最新部署对应这次数据提交；
- `public/feed.xml` 存在且可被 Atom 阅读器解析。

日报工作流按 `Asia/Shanghai` 07:40 启动、08:10 补跑。GitHub 的计划任务不是分钟级 SLA，高负载时可能延后数小时。

## 4. 快照保留

每次正式发布或当日修订都会在 `public/releases/` 写入一个完整快照（约 16 MB）。发布脚本最多保留 7 个，并始终保留当前版本及其初版、上一版（深读恢复和修订对比要用）。过期快照删除后，旧分享链接仍可通过 `public/data/edition-versions/<releaseId>.json` 打开当期日报与深读。

需要手动清理时运行：

```bash
python scripts/publication.py prune --public public
```

## DeepSeek V4 Flash 中文标题、摘要和关键事实（推荐）

在 GitHub 仓库打开 `Settings → Secrets and variables → Actions`：

Actions Secrets：

- `DEEPSEEK_API_KEY`：DeepSeek 控制台生成的密钥，只放在加密 Secret。

Actions Variables：

- `AI_PROVIDER=deepseek`
- `DEEPSEEK_MODEL=deepseek-v4-flash`

密钥由 GitHub Actions 的 Python 采集脚本在服务端读取，Cloudflare 只托管生成后的静态 JSON；不要把密钥设置为 Worker 公开环境变量、写进 `public/`、提交到仓库或放入浏览器 JavaScript。没有 API Key 时，采集、Top 10 规则筛选和保守摘要仍会正常运行，但系统不会假装已经完成中文翻译。

依次手动运行 `Daily news update` 和 `Full stream update`，再检查：

- `public/data/news.json.selectionMethod` 应为 `deepseek`，`selectionStrategy` 应为 `ai-ranked-rule-constrained`；只有 AI 评分调用或解析失败时才为 `rules` / `rules-diverse`；
- `selectionStatus=adjusted` 是程序按主题/来源配额进行的正常校正，不是降级；真正的 AI 评分回退为 `fallback`；
- `public/data/news.json.translationStatus` 应为 `ok`，`translationModel` 应为 `deepseek-v4-flash`，`translatedItemCount` 应为 `10`；
- 每条应有 `title`、`originalTitle`、`summary` 和非空 `keyFacts`；
- `sources`、`scoreReasons` 和 `confidenceReason` 应非空。
- `public/data/research.json.translatedItemCount` 和 `public/data/stream.json.translatedItemCount` 应大于 0。

若只希望使用 OpenAI，改为 `AI_PROVIDER=openai`，并配置 Secret `OPENAI_API_KEY` 与 Variable `OPENAI_MODEL`。完整说明、降级语义和论文采集词示例见 README 的“启用 DeepSeek V4 Flash 中文翻译”。

## 邮件推送（可选）

邮件由每日工作流在数据验证成功并提交后发送。公开网页不收集访客邮箱；管理员在加密 Secrets 中维护收件人。

Actions Secrets：

- `SMTP_HOST`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`（多个地址用逗号或分号）
- `EMAIL_REPLY_TO`（可选）

Actions Variables：

- `SMTP_PORT=587`
- `SMTP_USE_SSL=false`
- `SMTP_STARTTLS=true`
- `SITE_URL=https://newsfrontier.top`（换域名后同步修改）

端口 465 通常改为 `SMTP_USE_SSL=true`。未配置核心邮件变量时会安全跳过，不会阻断日报更新。SMTP 凭证应使用服务商提供的授权码，不要提交登录密码或收件人清单。

## 验收清单

- 首页可以搜索、分类、排序、查看“为什么重要”并打开原文。
- 页面显示最新生成日期与 10 条重点事件。
- 历史页可切换日期；输入关键词后能检索多个日期。
- 收藏页刷新后仍保留内容；关注页能添加与删除本机关注词。
- 论文雷达可保存、删除最多 20 个个人关键词；“我的论文流”能筛选并高亮命中，系统采集词列表可见。
- 每条新闻可展开关键事实、多来源、置信度与评分解释。
- 搜索索引清单按月加载 `search-YYYY-MM.json`，展开搜索结果时再请求当期完整归档。
- `/feed.xml` 可订阅；单条新闻的复制链接能定位到 `#item-...`。
- `public/data/status.json` 显示 `state: ok`；模拟失败时网页出现更新失败警告且不回退样例。
- GitHub Actions 的 CI、Daily news update 均为绿色。
- `https://newsfrontier.top/` 使用 HTTPS 正常访问。
- `Production smoke test` 通过，CSP、`nosniff` 和各类 JSON 的 `Cache-Control` 没有缺失或重复。
- 自定义域名状态为 `Active`，且 DNS 没有重复 A/AAAA/CNAME 记录。

## 常见故障

- `Only N eligible candidates`：有效候选不足 10 条，脚本会拒绝覆盖上一期；稍后手动重试或维护 `config/news_config.json` 中的信源。
- RSS/GDELT 出现 `403`、`429` 或超时：其他信源仍会继续；持续失败时替换该信源。
- DeepSeek/OpenAI 候选评分调用或结构化输出解析失败：`selectionMethod` 切换为 `rules`、`selectionStatus` 为 `fallback`；最终规则 Top 10 仍会进入独立中文翻译阶段。类别/来源集中则由程序正常校正为 `adjusted`，不会再误报为 AI 失败。
- 页面显示“翻译不完整”：日报查看 `status.json.translationDiagnostics`，全量动态查看 `stream-status.json.translationDiagnostics`，论文查看 `status.json.researchEditorialDiagnostics`；其中记录缺失 ID、逐项原因、拆分重试次数和最终完成原因。成功条目会被缓存，稍后重跑只补缺失项。
- 页面显示“今日待更新”：当前栏目的版本日期仍早于北京时间今天；08:00 后检查日报工作流、信源和 Cloudflare 最新部署。
- 页面显示“最近一次自动更新失败”：打开 `public/data/status.json` 或 Actions 日志查看已公开的简短原因；上一期数据不会被覆盖。
- 邮件未发送：先确认工作流中 `Send administrator email digest` 步骤是否显示跳过配置；再核对 SMTP 端口、SSL/STARTTLS 和授权码。
- `git push` 被拒绝：两个数据工作流共用 `frontier-data-main` 并发锁，并会执行最多三次冲突安全的 rebase/push；若仍失败，再检查 Actions 的 `Read and write permissions` 和 `main` 分支保护规则。
- 站点没有更新：在 Worker 的 `Deployments` 中查看最新构建日志，确认连接的是 `voilalz/frontier-pulse` 的 `main`，部署命令为 `npx wrangler deploy`。
- 自定义域名证书未签发：检查 DNS 是否存在冲突记录，并确认该域名确实属于当前 Cloudflare Zone。

## 线上响应头与缓存验收

Workers 静态资源会直接应用 `public/_headers`；若以后为 Worker 增加脚本，需要在脚本响应中保留同等响应头。部署后运行：

```bash
curl -fsSI https://你的域名/
curl -fsSI https://你的域名/data/news.json
curl -fsSI https://你的域名/data/status.json
curl -fsSI https://你的域名/data/archive/search-index.json
python scripts/check_production.py --site-url https://你的域名/
```

预期首页有 CSP、`X-Content-Type-Options: nosniff`；`news.json` 为 `max-age=300`，`status.json` 为 `max-age=60`，归档与搜索清单为 `max-age=300`。同一个响应不应出现两组 `max-age`。常规前端请求不追加时间戳，只有用户主动点击刷新时才绕过缓存。

## 发布与恢复

整期快照与单命令恢复见上文“快照保留”；恢复已保留的版本可手动运行 `Restore retained release` 工作流。外部监测器（`ops/watchdog`）默认不部署。
