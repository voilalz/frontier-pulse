# 经典论文目录录入

截至 2026-10-01，五领域各 **40/40**，合格论文 **200/200**，候选和跨域冲突均为 **0**。真实书目与两项独立经典依据已逐篇审阅，严格门禁通过。完整全文导读仍为 **0/30**。测试里的人工样例不属于此目录，目录合格也不代表经典栏目已经接入页面或发布流程。参见 `docs/classic-paper-index.md` 和 `docs/audits/2026-10-01-classic-sources/`。

## 使用

```sh
python scripts/classic_catalog.py --as-of 2026-10-01
python scripts/classic_catalog.py --as-of 2026-10-01 --require-complete \
  --report docs/audits/2026-10-01-classic-sources/inventory.json
```

普通模式的 `ok: true` 表示输入结构和已有核验记录可接受；`complete: false` 明确表示目录未满足 200/40 配额。后续出版门禁必须使用 `--require-complete`；本次该命令退出 0，确认真实 200/40 配额。工具完全离线，不抓 URL、不调用模型、不改新闻、页面或生产数据。

每篇先以 `candidate` 录入，身份字段不能造假；经过逐篇来源核验后才改为 `verified`。无 DOI 的早期论文使用稳定 `classic:` 内部 ID 和出版者/作者页，不生成伪 DOI。预印本与正式版写在同一记录，arXiv 版本号不会增加身份；跨领域只选一个 `primaryDomain`。

`bibliographicEvidence` 至少一个可审阅的出版者、作者或 DOI 注册机构来源。保存原文文本捕获（UTF-8），`capture.path` 相对本目录，`capture.sha256` 是实际文件哈希；保存 URL、带时区的核验时间、页码/章节/位置、连续引文、`reviewed: true` 及 `observed` 元数据。规范题名、完整作者、年份、载体和每个标识符应与捕获引文一致。使用精确发表日期时也须在来源中核对。

`classicEvidence` 至少两个独立提供方的综述、课程、奖项或长期基准来源，包含相同的捕获/核验字段和 `supportsPaperId`。引文须能定位该论文（题名、别名或核验标识符）；`classicRationale` 解释奠基方法或长期影响。仅引用量不合格。镜像应记录 `originUrl`；同一机构拥有多个域名时用一致的 `providerGroup` 声明，不能通过改机构名称绕开独立性。

工具校验字段、审阅声明、原文片段存在、哈希和规则，不能证明捕获一定来自宣称 URL，也不能代替人工判断经典性、完整作者或机构所有权。新增论文需要保留实际检索/抓取记录；未核实内容保持候选。

只有年份的临界五年论文保守等到该年末周年；具体日期有依据后可按日期资格放行。正文导读、全文哈希和页码定位在下一阶段单独验收。

完整格式见 `docs/superpowers/specs/2026-10-01-classic-catalog.md`；拒绝边界见 `tests/test_classic_catalog.py`，其中样例仅用于测试。

交付捕获位于 `evidence/<FIELD>/`。各编号块是分别定位的真实必要摘录或明确追溯的确定性书目渲染；同文件多个块不代表一段连续原文。`contextSummary` 是人工复述，不是引文。原始响应、提取文本、实际上下文与精简捕获的哈希各自对应不同字节；来源谱系见各领域 `provenance.json`。完整第三方源文属于未分发的研究中间材料。
