# 每日深读编辑内容模型 v2

`public/data/deepread.json` 与每日日期归档共享这一模型。`schemaVersion: 1` 的历史归档仍由网页旧渲染器读取。生成修订号为 7；发布日期采用北京时间，事件材料限定为生成时前 24 小时内有可验证发布时间的新闻。

## 公共数据契约

```json
{
  "schemaVersion": 2,
  "generationRevision": 7,
  "editionDate": "2026-09-27",
  "generatedAt": "2026-09-26T23:07:00Z",
  "headline": "项目从准备进入试验记录",
  "lead": "今天公布的结果补上了前次报道尚未发生的测试节点。",
  "chapters": [
    {
      "id": "chapter-1",
      "kind": "event",
      "comparisonKey": "",
      "comparisonNote": "",
      "title": "一次任务进展",
      "angle": "前次安排与今天结果的差异",
      "newsIds": ["news-1"],
      "blocks": [
        {"type": "paragraph", "text": "今天公开了实际测试记录。", "newsIds": ["news-1"]},
        {"type": "change", "text": "此前报道测试安排；今天公布了完成后的结果。", "newsIds": ["news-1"]}
      ]
    }
  ],
  "observations": [],
  "events": [
    {
      "newsId": "news-1",
      "eventId": "evt-1",
      "title": "项目公布试验结果",
      "originalTitle": "The project reports trial results",
      "excerpt": "项目公布已完成的测试及后续安排。",
      "category": "航空航天",
      "publishedAt": "2026-09-26T18:00:00Z",
      "sources": [{"name": "原发布方", "url": "https://example.org/release"}],
      "image": "",
      "imageSource": "",
      "evidenceLevel": "primary",
      "deltaScore": 2,
      "history": [{"editionDate": "2026-09-25", "newsId": "older-1", "title": "项目宣布测试安排", "source": "原发布方"}]
    }
  ],
  "candidateCount": 12,
  "eventCount": 1,
  "sourceCount": 1,
  "generationStatus": "insufficient",
  "warnings": ["本期合格独立事件不足4项，按实际数量刊发简版。"]
}
```

示例展示稀疏期的字段形状，内容不是线上报道。正常期选取 4～6 件正文核心事件，最多 12 件仅在候选池；`events` 目录与 `chapters[].newsIds` 一一对应。`paragraph` 表示正文段落；`change` 只能引用有同一 `eventId` 此前记录的单件新闻。段落 `newsIds` 可用于各渠道在本节末尾生成原文引用；不可将模型生成的来源、链接或图片写入目录。

`kind: comparison` 章节仅比较 2～3 件不同事件，它们须共享具体 `comparisonKey`，例如 `ai-agent`。每个事件有单独事实段，另有引用全部章节成员的 `type: comparison` 段落。该章节固定显示 `comparisonNote: "并列比较不代表事件之间存在因果关系。"`；大类或宽泛相似性不足以组成比较章。无支持时拆成独立事件章节。候选优先级以重要度为主，已核验同一事件的实质行动变化用 `deltaScore`（0 / 2 / 3）加分，当前一手来源与独立多源也可在相近重要度时加分。

`observations` 仅在完整正文且全部证据通过时包含 2～3 条，每条 `{text, newsIds, supports:[{newsId, supportQuote}]}`，20～80 字，关联 1～2 件入选事件；`supportQuote` 必须逐字出自对应的清洁摘要或证据，供编辑追查。程序还会拒绝引文不能支撑的绝对化范围与明显从谨慎材料跃迁到确定结论的表述；这不能取代编辑对判断含义的审校。校验失败则观察清空，并标记 `generationStatus: partial`。正文不足时观察为空数组。政治、政策与“局部冲突”交战时事从新生成的深读候选及历史记录排除；技术装备试验仍可入选。其他新闻栏目和旧日期归档不改。

证据等级取值为 `primary`（一手来源）、`multi`（当期至少两个独立来源组）、`single`（当期单一独立来源组）、`opinion`（明确标记的观点材料）。一手指经过信源配置标识的机构/原发布方材料；多个转载链接若属于同一证据组，仍为 `single`。带发布时间的过期来源不进入当期引用目录，也不能抬高证据等级。标签说明**材料类型**，不保证逐句事实核验。归属与不确定性需要在对应事实附近准确表述，统一说明放在排版层的来源说明处。

历史变化只引用同一 canonical `eventId` 在本期之前的时间线。生成器会同时检查既有记录的译文标题、原文标题和摘要开头；旧记录可用搜索归档或事件身份记录补足核验材料。缺少核验材料时不生成这条历史对照。完整写作失败会重试，随后按章节恢复通过校验的段落，并以 `generationStatus: partial` 标识简版。

## 渠道映射

| 共同字段 | 网站 | 微信公众号日报 | 邮件日报 |
| --- | --- | --- | --- |
| `headline`、`lead` | 文章头部 | 图文标题及开篇 | 主题行及导语 |
| `chapters[].blocks[]` | 连贯段落与变化强调 | 按正文段落排版 | HTML/纯文本段落 |
| `chapters[].kind`、`comparisonNote` | 比较章显示非因果说明 | 同章节并列呈现 | 同章节并列呈现 |
| `observations[]` | 短观察及关联原报道 | 文章末尾短观察 | 文章末尾短观察 |
| `events[]` | 本节资料、证据标签、来源配图 | 文末参考资料与授权图片 | 原始报道链接 |
| `generationStatus` | 完整版或简版提示 | 发布前编辑门控 | 发送前编辑门控 |

渠道适配器只负责排版、图片尺寸与超链接形式；同一期的事件身份、正文段落和引用目录来自同一份 JSON。微信公众号推送及邮件发送需要独立的账号、模板和发布流程，本次契约不直接调用这些渠道。
