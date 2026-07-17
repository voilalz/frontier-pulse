# Cloudflare Pages + GitHub Actions 上线清单

## 方案 A：Cloudflare Git Integration（推荐）

这是步骤最少、维护成本最低的方式。GitHub Actions 负责每天生成并提交数据，Cloudflare 检测到 `main` 更新后自动发布。

### 1. 开启 GitHub Actions 写权限

打开 <https://github.com/voilalz/frontier-pulse/settings/actions>：

1. 找到 `Workflow permissions`。
2. 选择 `Read and write permissions`。
3. 保存。

如 `main` 启用了分支保护，需要允许 `github-actions[bot]` 更新 `public/data/news.json`，或为自动数据提交设置对应例外。

### 2. 连接 Cloudflare Pages

1. 登录 Cloudflare Dashboard。
2. 进入 `Workers & Pages → Create application → Pages → Connect to Git`。
3. 授权 GitHub，并选择 `voilalz/frontier-pulse`。
4. Production branch：`main`。
5. Framework preset：`None`。
6. Build command：留空。
7. Build output directory：`public`。
8. Root directory：仓库根目录。
9. 保存并部署。

首次完成后会得到 `https://frontier-pulse.pages.dev`，若名称被占用，Cloudflare 会提供带后缀的实际地址。

### 3. 运行一次日报

进入仓库 `Actions → Daily news update → Run workflow`。成功标准：

- 工作流绿色通过；
- `public/data/news.json` 包含 `timezone: Asia/Tokyo`；
- `items` 恰好为 10 条；
- Cloudflare Deployment 对应最新提交。

之后工作流会在每天 `Asia/Tokyo 08:00` 自动运行。GitHub 的计划任务不是分钟级 SLA，高负载时可能延后。

## 方案 B：Wrangler Direct Upload（可选）

只在你希望 GitHub Actions 直接控制部署、而不是让 Cloudflare 监听 Git 提交时使用。Direct Upload 项目之后不能原地切换为 Git Integration；二选一即可。

1. 在 Cloudflare 创建名为 `frontier-pulse` 的 Direct Upload Pages 项目。
2. 创建 API Token，权限设置为 `Account → Cloudflare Pages → Edit`。
3. 在 GitHub Actions Secrets 中添加：
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`
4. 在 GitHub Actions Variables 中添加：
   - `CLOUDFLARE_DEPLOY_ENABLED=true`
5. 手动运行 `Deploy Cloudflare Pages`，或推送 `public/` 目录更新。

`.github/workflows/pages-deployment.yml` 使用 Wrangler 将 `public` 目录部署到 `frontier-pulse` 项目。未设置启用变量时，该部署任务会安全跳过，不影响推荐的 Git Integration 方案。

## AI 中文标题、摘要和关键事实（推荐）

在 GitHub Actions Secrets 中添加 `OPENAI_API_KEY`。可在 Variables 中设置 `OPENAI_MODEL`；未设置时使用仓库默认的 `gpt-5.6-luna`。没有 API Key 时，采集、Top 10 规则筛选和保守摘要仍会正常运行，但系统不会假装已经完成中文翻译。

手动运行后检查 `public/data/news.json`：

- `method` 应为 `openai`；
- 每条应有 `title`、`originalTitle`、`summary` 和非空 `keyFacts`；
- `sources`、`scoreReasons` 和 `confidenceReason` 应非空。

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
- `SITE_URL=https://frontier-pulse.jiumi674.workers.dev`（换域名后同步修改）

端口 465 通常改为 `SMTP_USE_SSL=true`。未配置核心邮件变量时会安全跳过，不会阻断日报更新。SMTP 凭证应使用服务商提供的授权码，不要提交登录密码或收件人清单。

## 绑定 `news.frontier.com`

只有在你拥有 `frontier.com` 或获得其 DNS 管理权限时才能使用这个子域名。

1. 在 Pages 项目打开 `Custom domains → Set up a custom domain`。
2. 输入 `news.frontier.com`。
3. 如果 `frontier.com` 的 DNS 已托管到同一 Cloudflare 账户，系统会自动创建记录和 TLS 证书。
4. 如果 DNS 在其他服务商，按 Cloudflare 显示的目标创建 CNAME，并等待证书变为 `Active`。

若你不控制 `frontier.com`，请改用自己拥有的域名，例如 `news.你的域名.com`；仅修改网页代码无法取得第三方域名。

## 验收清单

- 首页可以搜索、分类、排序、查看“为什么重要”并打开原文。
- 页面显示最新生成日期与 10 条重点事件。
- 历史页可切换日期；输入关键词后能检索多个日期。
- 收藏页刷新后仍保留内容；关注页能添加与删除本机关注词。
- 每条新闻可展开关键事实、多来源、置信度与评分解释。
- `public/data/status.json` 显示 `state: ok`；模拟失败时网页出现更新失败警告且不回退样例。
- GitHub Actions 的 CI、Daily news update 均为绿色。
- Cloudflare Pages 使用 HTTPS 正常访问。
- 自定义域名状态为 `Active`，且 DNS 没有重复 A/AAAA/CNAME 记录。

## 常见故障

- `Only N eligible candidates`：有效候选不足 10 条，脚本会拒绝覆盖上一期；稍后手动重试或维护 `config/news_config.json` 中的信源。
- RSS/GDELT 出现 `403`、`429` 或超时：其他信源仍会继续；持续失败时替换该信源。
- OpenAI 调用失败：自动降级到规则筛选，不阻断日报。
- 页面显示“数据过期”：`generatedAt` 已超过 36 小时；检查日报工作流、信源和 Cloudflare 最新部署。
- 页面显示“最近一次自动更新失败”：打开 `public/data/status.json` 或 Actions 日志查看已公开的简短原因；上一期数据不会被覆盖。
- 邮件未发送：先确认工作流中 `Send administrator email digest` 步骤是否显示跳过配置；再核对 SMTP 端口、SSL/STARTTLS 和授权码。
- `git push` 被拒绝：检查 Actions 的 `Read and write permissions` 和 `main` 分支保护规则。
- Pages 没有更新：确认项目连接的是 `voilalz/frontier-pulse` 的 `main`，输出目录为 `public`。
- 自定义域名证书未签发：检查 DNS 是否存在冲突记录，并确认该域名确实属于当前 Cloudflare Zone。
