# 智域前沿 / Frontier Pulse

面向全球科技、AI、航空航天、军事动态、局部冲突、前沿技术与无人系统的自动日报。网站不需要常驻服务器：Cloudflare Pages 托管静态页面，GitHub Actions 每天 `Asia/Tokyo 08:00` 抓取最近 24 小时的公开新闻、筛选 Top 10、生成中文摘要并发布。

仓库：<https://github.com/voilalz/frontier-pulse>

## 工作方式

1. 并行读取 GDELT 与公开 RSS/Atom 信源。
2. 清洗链接、去重、分类，并按时效、来源、主题与多源印证评分。
3. 配置 `OPENAI_API_KEY` 时，调用 OpenAI Responses API 完成 Top 10 编辑筛选与中文摘要；没有密钥时自动使用确定性规则和保守摘要。
4. 只有在输出恰好为 10 条且字段校验通过时，才覆盖 `public/data/news.json`。
5. GitHub Actions 提交新一期数据；Cloudflare Pages 自动部署到全球边缘网络。

## 目录

```text
public/                         Cloudflare Pages 发布目录
  index.html                    网站入口
  data/news.json                最新一期 Top 10
scripts/update_news.py          采集、去重、评分、摘要与输出
config/news_config.json         主题、信源、权重、时区和模型配置
tests/                          离线测试与固定样例
.github/workflows/
  ci.yml                        每次提交/PR 的测试
  daily-news.yml                每天 08:00 自动更新
  pages-deployment.yml          可选：Wrangler 直接部署
legacy-offline/                 离线数据导入说明与样例
```

## 本地运行

只依赖 Python 3.11+ 标准库：

```bash
python -m unittest discover -s tests -v
python scripts/update_news.py \
  --fixture tests/fixtures/articles.json \
  --output public/data/news.json \
  --skip-ai \
  --now 2026-07-16T00:00:00Z
python -m http.server 8000 --directory public
```

访问 `http://localhost:8000`。实时抓取使用：

```bash
python scripts/update_news.py --output public/data/news.json
```

## 最简上线方式（推荐）

1. 在 GitHub 仓库 `Settings → Actions → General → Workflow permissions` 选择 `Read and write permissions`。
2. 在 Cloudflare Dashboard 选择 `Workers & Pages → Create → Pages → Connect to Git`，连接本仓库。
3. 设置 Production branch 为 `main`、Framework preset 为 `None`、Build command 留空、Build output directory 为 `public`。
4. 在 GitHub `Actions → Daily news update → Run workflow` 手动运行一次并确认产生 10 条新闻。

这一模式不需要 Cloudflare API Token；后续每日数据提交会触发 Pages 自动部署。完整账户配置和自定义域名步骤见 [DEPLOY_CLOUDFLARE.md](DEPLOY_CLOUDFLARE.md)。

## 可选配置

GitHub `Settings → Secrets and variables → Actions`：

- Secret `OPENAI_API_KEY`：启用 AI Top 10 编辑与中文摘要。
- Variable `OPENAI_MODEL`：可选，默认 `gpt-5-nano`。
- 若改用 Wrangler Direct Upload，再配置 `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`，并把 Variable `CLOUDFLARE_DEPLOY_ENABLED` 设为 `true`。

密钥只能存放在 GitHub Secrets 或本地环境变量中，不能提交到仓库。

## 调整时间与主题

计划任务使用 GitHub Actions 的 IANA 时区配置：

```yaml
- cron: "0 8 * * *"
  timezone: "Asia/Tokyo"
```

主题、信源、权重和 24 小时窗口在 `config/news_config.json` 中调整。GitHub 计划任务在平台繁忙时可能延迟数分钟。

## 数据与版权边界

- 只保存标题、短摘要、来源和原文链接，不镜像新闻全文。
- AI 只能依据候选标题和 RSS 描述生成摘要，提示词禁止补写无证据事实。
- 任一信源故障不会中断其他信源；有效候选不足 10 条时保留上一期数据。
- 军事与冲突内容使用中性表述，关键结论应回到原始来源并交叉验证。
