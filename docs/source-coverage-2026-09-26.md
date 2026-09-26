# 2026-09-26 信源有效覆盖审计

统计窗口：北京时间 **2026-09-25 08:59:15 至 2026-09-26 08:59:15**（UTC 00:59:15）。同一轮下载的 RSS/Atom 响应用于三组配置回放，避免把不同日期的新闻量变化误当成扩源效果。

## 结果

| 配置 | RSS/Atom 入口 | 有效独立候选 | 说明 |
|---|---:|---:|---|
| 原配置 | 31 | 92 | 保留原有信源属性 |
| 原入口 + 专业主题属性 | 31 | 111 | 专业频道可识别型号、任务等缺少泛化关键词的报道 |
| 完整扩源配置 | 60 | 168 | 51 个订阅域名，新增 29 个入口 |

扩源配置有 302 条时间合格的原始候选；选题规则排除 12 条、主题过滤排除 120 条，得到 170 条，跨来源去重后剩余 168 条。60 个入口均可访问，其中 38 个当期贡献合格候选，另有 22 个当期无合格产出。专业属性仅用于明确聚焦的机构/主题频道，综合国际新闻源仍须通过主题判断。

| 主题 | 独立候选 |
|---|---:|
| AI | 41 |
| 航空航天 | 31 |
| 军事动态 | 26 |
| 局部冲突 | 14 |
| 前沿技术 | 25 |
| 无人系统 | 31 |

AI、航空航天、无人系统、前沿技术合计 **128 条，占 76.2%**。军事与冲突合计 40 条，占 23.8%。本次快照进入 100–300 条目标区间；单个窗口不能保证每天达标，后续由每轮 `source-health.json` 连续记录。

## 统计边界

- 只计明确的发布时间落在前 24 小时内的条目；Atom 的更新时间不能替代发布时间。
- 排除以中国及中国机构/企业为主要对象的条目、商业推广和非目标主题；不按媒体注册地过滤。
- 日期缺失、未来条目、旧闻、缓存恢复、放宽时间窗补采均不计入目标。
- 使用生产采集、选题过滤、主题识别和同事件去重代码；不以展示上限或 LLM 翻译上限裁剪审计数据。
- “有效候选”是通过上述确定性规则的编辑候选，不代表每条已获得完整正文或完成逐句人工事实核验。
- 60 个入口不等于 60 家独立出版机构；同域主题频道分开采集，独立候选统一去重。
- 原配置的 92 → 111 来自专业主题识别，111 → 168 来自新增入口及其去重后的贡献，不应全归因于新增媒体。

## 逐入口实测

| 来源与订阅地址 | 窗口内原始条目 | 合格条目 | 去重后主来源贡献 |
|---|---:|---:|---:|
| [NASA](https://www.nasa.gov/feed/) | 9 | 9 | 9 |
| [European Space Agency](https://www.esa.int/rssfeed/Our_Activities/Space_News) | 4 | 4 | 4 |
| [SpaceNews](https://spacenews.com/feed/) | 0 | 0 | 0 |
| [FlightGlobal](https://www.flightglobal.com/rss) | 10 | 10 | 10 |
| [Breaking Defense](https://breakingdefense.com/feed/) | 7 | 4 | 4 |
| [Defense News](https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml) | 8 | 8 | 8 |
| [C4ISRNET](https://www.c4isrnet.com/arc/outboundfeeds/rss/?outputType=xml) | 2 | 2 | 2 |
| [Defense One](https://www.defenseone.com/rss/all/) | 2 | 2 | 2 |
| [DARPA](https://www.darpa.mil/rss.xml) | 0 | 0 | 0 |
| [The War Zone](https://www.twz.com/feed) | 4 | 4 | 4 |
| [BBC World](https://feeds.bbci.co.uk/news/world/rss.xml) | 26 | 6 | 6 |
| [Al Jazeera](https://www.aljazeera.com/xml/rss/all.xml) | 25 | 5 | 5 |
| [MIT Technology Review](https://www.technologyreview.com/feed/) | 3 | 3 | 3 |
| [IEEE Spectrum](https://spectrum.ieee.org/feeds/feed.rss) | 1 | 0 | 0 |
| [Ars Technica](https://feeds.arstechnica.com/arstechnica/technology-lab) | 0 | 0 | 0 |
| [TechCrunch AI](https://techcrunch.com/category/artificial-intelligence/feed/) | 17 | 17 | 17 |
| [Google DeepMind](https://deepmind.google/blog/rss.xml) | 0 | 0 | 0 |
| [Hugging Face](https://huggingface.co/blog/feed.xml) | 0 | 0 | 0 |
| [JAXA](https://global.jaxa.jp/rss/press.rdf) | 1 | 1 | 1 |
| [Naval News](https://www.navalnews.com/feed/) | 4 | 4 | 4 |
| [DroneLife](https://dronelife.com/feed/) | 4 | 4 | 4 |
| [sUAS News](https://www.suasnews.com/feed/) | 7 | 7 | 7 |
| [The Robot Report](https://www.therobotreport.com/feed/) | 4 | 4 | 4 |
| [MIT News AI](https://news.mit.edu/rss/topic/artificial-intelligence2) | 1 | 1 | 1 |
| [Google Research](https://research.google/blog/rss/) | 0 | 0 | 0 |
| [NVIDIA Blog](https://blogs.nvidia.com/feed/) | 0 | 0 | 0 |
| [Phys.org Technology](https://phys.org/rss-feed/technology-news/) | 14 | 1 | 1 |
| [ScienceDaily Engineering](https://www.sciencedaily.com/rss/matter_energy/engineering.xml) | 0 | 0 | 0 |
| [France 24](https://www.france24.com/en/rss) | 24 | 5 | 5 |
| [Deutsche Welle](https://rss.dw.com/rdf/rss-en-all) | 20 | 4 | 4 |
| [The Guardian World](https://www.theguardian.com/world/rss) | 29 | 6 | 6 |
| [OpenAI](https://openai.com/news/rss.xml) | 1 | 1 | 1 |
| [Microsoft Research](https://www.microsoft.com/en-us/research/feed/) | 0 | 0 | 0 |
| [Google AI](https://blog.google/innovation-and-ai/technology/ai/rss/) | 0 | 0 | 0 |
| [Apple Machine Learning](https://machinelearning.apple.com/rss.xml) | 0 | 0 | 0 |
| [The Decoder](https://the-decoder.com/feed/) | 9 | 9 | 9 |
| [NASASpaceflight](https://www.nasaspaceflight.com/feed/) | 0 | 0 | 0 |
| [Spaceflight Now](https://spaceflightnow.com/feed/) | 1 | 1 | 1 |
| [Universe Today](https://www.universetoday.com/rss.xml) | 1 | 0 | 0 |
| [Astronomy](https://www.astronomy.com/feed/) | 5 | 1 | 1 |
| [Aerospace Testing International](https://www.aerospacetestinginternational.com/feed) | 1 | 1 | 1 |
| [Unmanned Airspace](https://www.unmannedairspace.info/feed/) | 10 | 10 | 10 |
| [DroneDJ](https://dronedj.com/feed/) | 5 | 4 | 4 |
| [Physics World](https://physicsworld.com/feed) | 3 | 2 | 2 |
| [Quanta](https://www.quantamagazine.org/feed/) | 1 | 1 | 1 |
| [Quantum Computing Report](https://quantumcomputingreport.com/feed/) | 10 | 10 | 10 |
| [The Quantum Insider](https://thequantuminsider.com/feed/) | 10 | 8 | 8 |
| [Semiconductor Engineering](https://semiengineering.com/feed/) | 2 | 2 | 2 |
| [EE Times](https://www.eetimes.com/feed/) | 2 | 1 | 1 |
| [Science News](https://www.sciencenews.org/feed) | 2 | 0 | 0 |
| [ScienceDaily AI](https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml) | 1 | 1 | 1 |
| [ScienceDaily Robotics](https://www.sciencedaily.com/rss/matter_energy/robotics.xml) | 0 | 0 | 0 |
| [ScienceDaily Quantum Computing](https://www.sciencedaily.com/rss/matter_energy/quantum_computing.xml) | 1 | 1 | 0 |
| [ScienceDaily Materials](https://www.sciencedaily.com/rss/matter_energy/materials_science.xml) | 0 | 0 | 0 |
| [ScienceDaily Space](https://www.sciencedaily.com/rss/space_time.xml) | 2 | 0 | 0 |
| [ScienceDaily Nanotechnology](https://www.sciencedaily.com/rss/matter_energy/nanotechnology.xml) | 0 | 0 | 0 |
| [Tech Xplore AI](https://techxplore.com/rss-feed/machine-learning-ai-news/) | 6 | 6 | 5 |
| [Tech Xplore Robotics](https://techxplore.com/rss-feed/robotics-news/) | 0 | 0 | 0 |
| [Tech Xplore Semiconductors](https://techxplore.com/rss-feed/semiconductors-news/) | 0 | 0 | 0 |
| [Tech Xplore Engineering](https://techxplore.com/rss-feed/engineering-news/) | 3 | 0 | 0 |

去重后的主来源贡献按保留条目的主来源归属，不把同事件的辅助来源重复计数。零产出可以是当天未更新、发布时间不在窗口内或主题/选题过滤的结果，不等同于抓取失败。未纳入配置的候选包括返回 403 的 AI News、Unite.AI，以及未返回有效新闻项的 Space.com 试探地址。

## 复核与持续监测

```bash
python scripts/audit_sources.py --config config/news_config.json --output /tmp/source-health.json
```

此命令审计运行时的滚动窗口，结果会随新闻更新变化。本次聚合快照（不含新闻正文）保存在：

- [原配置快照](audits/sources-2026-09-26-baseline.json)
- [原入口加专业属性快照](audits/sources-2026-09-26-scoped.json)
- [扩源后快照](audits/sources-2026-09-26-expanded.json)
