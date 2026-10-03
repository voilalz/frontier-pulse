# AI 六篇全文导读审计

审计冻结核对时间：2026-10-03T08:09:03.574379+00:00。导读验收 as-of 为 2026-10-03；目录锚点仍为 2026-10-01。

本次交付为六篇已有 verified AI 身份的原创中文导读，状态 ready 表示本字段作者工作完成、可进入独立审查。此前未封存的 sequence-four 文件在维护中丢失；本次 PDF 在 2026-10-02 重新下载，重新逐页提取和复核，不声称遗失文件得到恢复。后续中断保留了这些新文件，本次仅完成窗口与冻结复查，保留真实的 10 月 2 日下载和完整阅读时间。

方法链由词表示进入优化，再比较变分生成与对抗生成，随后阅读在线强化学习与注意力转导。该排序属于读者组织建议，不是各作者宣称的历史依赖。没有改写目录身份、年份或经典证据。

## 六个身份、预算和证据

长度按门禁的 Han 与非空白 Unicode 字符分别计算。正文长度只含六节，不含标题、元数据和证据注释。177 个证据窗口覆盖 123 个不同的 section/claim 组合；每个 claim 为对应正文的精确子串，七个区块均覆盖。逐字符覆盖检查无遗漏，但覆盖本身不能替代语义核验。

| 顺序 / ID | 主 PDF 页数 | 概览 Han / visible | 六节 Han / visible | 窗口数 | 完整阅读时间 UTC |
|---|---:|---:|---:|---:|---|
| 1 / `classic:ai:word2vec` | 12 | 184 / 201 | 607 / 673 | 28 | 2026-10-02T04:45:00.468513+00:00 |
| 2 / `classic:ai:adam` | 15 | 175 / 191 | 622 / 667 | 29 | 2026-10-02T04:45:00.470445+00:00 |
| 3 / `classic:ai:vae` | 14 | 187 / 199 | 617 / 668 | 33 | 2026-10-02T04:45:00.472136+00:00 |
| 4 / `classic:ai:gan` | 9 | 187 / 200 | 611 / 655 | 25 | 2026-10-02T04:45:00.474226+00:00 |
| 5 / `classic:ai:a3c` | 10 | 190 / 210 | 600 / 651 | 28 | 2026-10-02T04:45:00.475942+00:00 |
| 6 / `classic:ai:transformer` | 11 | 187 / 202 | 596 / 645 | 34 | 2026-10-02T04:45:00.478139+00:00 |

## 完整来源与实际字节

下列八个 PDF 的文件页数均由 pypdf 实际读取页树复查。六个主源合计 71 物理页；官方 A3C 补充 10 页与 Transformer 作者 v5 15 页另计 25 页，总计 96 物理页。两份 Transformer 有重合内容，96 不是独立研究内容的页数。所有正文和附录逐页读完，参考文献逐页扫描；页码均为从 1 开始的 PDF 文件索引。完整 PDF、提取文本、渲染和构建中间件仅位于 repo 外的 `guide-source-intermediates/AI/`。

提取采用各 JSON 声明的实际方法：pypdf PageObject.extract_text 默认模式，保留 Unicode 字符串，不归一化。页序、每页 text、PDF 绑定哈希及提取 JSON 的原始字节哈希均已检查。上下文 start/end 是 Python Unicode 字符偏移，以原样 text[start:end] 的 UTF-8 字节计算 SHA-256。

### word2vec

- 实际 URL：[源 PDF](https://arxiv.org/pdf/1301.3781v3)
- 文件：`AI/word2vec.pdf`；提取：`AI/word2vec.pages.json`。
- 下载 checkedAt：2026-10-02T04:26:16.839399+00:00；完整字节 228716；页数 12；阅读页 1–12。
- PDF SHA-256：`a44d7e22d2005752271c9cc1929c6462d4c8270916b063977992a883e3a54362`。
- 提取 JSON SHA-256：`159a50c08a8eb438a37c68cf7f61871dcb1eed7bbf91c4fab8b54189157eb032`。

### adam

- 实际 URL：[源 PDF](https://arxiv.org/pdf/1412.6980v9)
- 文件：`AI/adam.pdf`；提取：`AI/adam.pages.json`。
- 下载 checkedAt：2026-10-02T04:26:17.232518+00:00；完整字节 584641；页数 15；阅读页 1–15。
- PDF SHA-256：`eab9c73ae2ceda884b94830bda99312254bac4806f6c9f045cbab90721ecda31`。
- 提取 JSON SHA-256：`eaaae96fcc6555e47073df4cdbfa75738236919c516a399fd00d310c6f349bf9`。

### vae

- 实际 URL：[源 PDF](https://arxiv.org/pdf/1312.6114v10)
- 文件：`AI/vae.pdf`；提取：`AI/vae.pages.json`。
- 下载 checkedAt：2026-10-02T04:26:17.628454+00:00；完整字节 3926653；页数 14；阅读页 1–14。
- PDF SHA-256：`524a45520e6ad1f32c951f459e5a21c2698c29193b3b9b4826aa5655bd88d1de`。
- 提取 JSON SHA-256：`b3e656479f4372d65d53b33c904fc181699c02b155a397af2415679849c87a5a`。

### gan

- 实际 URL：[源 PDF](https://papers.nips.cc/paper_files/paper/2014/file/f033ed80deb0234979a61f95710dbe25-Paper.pdf)
- 文件：`AI/gan.pdf`；提取：`AI/gan.pages.json`。
- 下载 checkedAt：2026-10-02T04:26:18.441427+00:00；完整字节 539761；页数 9；阅读页 1–9。
- PDF SHA-256：`331961622a2f6588c48a34ecddc6a3d052ffe8fcfba333f233d5f27b2da5565d`。
- 提取 JSON SHA-256：`0adce7d38cafe400999be54f1814a9184352eaaa4fed4366a05a46405135fc2f`。

### a3c

- 实际 URL：[源 PDF](https://proceedings.mlr.press/v48/mniha16.pdf)
- 文件：`AI/a3c.pdf`；提取：`AI/a3c.pages.json`。
- 下载 checkedAt：2026-10-02T04:26:18.887597+00:00；完整字节 2455923；页数 10；阅读页 1–10。
- PDF SHA-256：`6548032d7105072e254872c82e02f82cbf34ea780eeed15454d90300b8fea563`。
- 提取 JSON SHA-256：`3dfd672ce051f63e8227666c83ec23e725e96ce4b37b314b3f9a46e9fa4c66a2`。

### transformer

- 实际 URL：[源 PDF](https://papers.nips.cc/paper_files/paper/2017/file/3f5ee243547dee91fbd053c1c4a845aa-Paper.pdf)
- 文件：`AI/transformer.pdf`；提取：`AI/transformer.pages.json`。
- 下载 checkedAt：2026-10-02T04:26:18.441813+00:00；完整字节 569417；页数 11；阅读页 1–11。
- PDF SHA-256：`d87d482d5ae7960e2e43d7dd6d21377e60e73e8fce1bf2a01aff7aca8a08c537`。
- 提取 JSON SHA-256：`33a1e6bf5f3dd57f571844bfcc8052db07707c383f8352ce0704d9745d5e5c54`。

### a3c-supp

- 实际 URL：[源 PDF](https://proceedings.mlr.press/v48/mniha16-supp.pdf)
- 文件：`AI/a3c-supp.pdf`；提取：`AI/a3c-supp.pages.json`。
- 下载 checkedAt：2026-10-02T04:26:18.862411+00:00；完整字节 1785618；页数 10；阅读页 1–10。
- PDF SHA-256：`0143dd1e90a47a82f56f6c9f54ae460e653ce60511271c757f87300b072adde3`。
- 提取 JSON SHA-256：`51089f3385ec68ffddc046a398e6d520336b1bf8859d84aaa6adad73593fa5b7`。

### transformer-author-v5

- 实际 URL：[源 PDF](https://arxiv.org/pdf/1706.03762v5)
- 文件：`AI/transformer-author-v5.pdf`；提取：`AI/transformer-author-v5.pages.json`。
- 下载 checkedAt：2026-10-02T04:26:16.841295+00:00；完整字节 2201700；页数 15；阅读页 1–15。
- PDF SHA-256：`bfaaec89262875f927cf1b38b2da2d775f3309b7bea3537f29b606ca67e79065`。
- 提取 JSON SHA-256：`3a2e0612ba495da6c6f00cee4f6e22b5384f871dc85c2de2ff79451fca1080ad`。

## 完整阅读和视觉复核范围

- word2vec：p.1–10 正文与 p.11 后续工作；p.11–12 参考文献扫描。复核 p.4/5 模型方向和复杂度、p.7/8 匹配训练条件及轮次表、p.9 句子补全组合表。
- Adam：p.1–9 机制、实验和扩展，p.10 结论，p.10–11 参考文献，p.12–15 收敛论证附录。复核 p.2 算法分母与逐元素操作、p.3 校正推导、p.4 理论假设、p.7 卷积曲线与 p.8 校正消融。阅读附录不表示独立证明其每个不等式正确。
- VAE：p.1–8 正文，p.9 参考文献及附录入口，p.10–14 附录 A–F（可视化、解析 KL、概率网络、边缘似然估计、MCEM、全 VB）。复核 p.3 下界、p.5 重参数化与目标、p.7 下界曲线、p.10 潜流形/样本、p.11 解析散度和概率解码器。
- GAN：p.1–7 正文/理论/实验/未来方向，p.8 对照表与致谢，p.8–9 参考文献。复核 p.3 博弈及替代目标、p.4 算法和最优判别器、p.5 JSD 与证明条件、p.6 Parzen 表、p.7 样本/最近训练样本/插值。
- A3C：主 p.1–8 正文及所有图表，p.9–10 参考文献。复核 p.4 优势公式与共享统计、p.5 曲线协议与汇总表、p.6 连续/迷宫结果及速度表、p.8 数据与时间轴。官方补充 p.1–10 全部复核，另看 p.4 算法 S2，p.5–9 图表；p.6/7 曲线为主要栅格图，未只依据提取出的图注判断。
- Transformer：正式 p.1–9 正文及图表，p.10–11 参考文献。复核 p.3 架构/遮罩、p.4 缩放与多头、p.6 复杂度与位置编码、p.8/9 翻译和变体表。作者 v5 的 p.1–15 另完整核对，p.8 的版本分数及 p.13–15 彩色注意力附录也已查看。

以上已查看的渲染共 39 个 PDF 页面，保存在 repo 外的 renders/。读取正文、附录与表图的记录是本作者的全文审核声明，后续独立审查应按已冻结的实际字节重查。

## 版本关系和结论边界

- `classic:ai:word2vec`：作者 arXiv:1301.3781v3（2013-09-07），12 页，含第 7 节后续工作；同一 ICLR 2013 目录身份的修订作者版，不把后续 NIPS 2013 方法并入主实验。
- `classic:ai:adam`：作者 arXiv:1412.6980v9（2017-01-30），15 页；页眉标注 Published as a conference paper at ICLR 2015，保留目录 ICLR 2015 身份；含收敛论证附录，非未经修订的 2015 原始字节。
- `classic:ai:vae`：作者 arXiv:1312.6114v10（2014-05-01），14 页，含附录 A–F；对应目录 ICLR 2014 论文的作者版，未采用 2022 v11 的排印修订。
- `classic:ai:gan`：NIPS 2014 正式论文集 PDF，9 页，Generative Adversarial Nets；正文、图表、参考文献均在此文件，无另列附录。
- `classic:ai:a3c`：ICML 2016 / PMLR 48 正式主论文 PDF，10 页（论文集页码 1928–1937）；官方补充材料另为 10 页，已完整复核并在审计单列，主证据 offsets 仅指本主文件。
- `classic:ai:transformer`：NIPS 2017 正式论文集 PDF，11 页，含翻译实验与参考文献；文件未附其正文提及的注意力可视化附录。作者 arXiv v5 的 15 页及新增解析实验另作版本核对，不迁移其结果。

- word2vec 的主方法是 CBOW/Skip-gram 与层次 softmax；没有把另篇 NIPS 2013 的负采样、短语学习等后续技术移入此篇。p.11 的代码和实体向量属于修订版后续工作，正文主实验与其分开。类比评测限制及共享机房 CPU 估计保留在导读中。
- Adam v9 的理论讨论采用在线凸设定、有界条件和衰减配置；p.6 明说分析不适用于非凸实验。没有把论文的收敛论证扩写成默认配置、所有非凸目标的无条件保证，也没有将训练损失优势等同于测试泛化。
- VAE 的对角高斯为示例选择；主方法连续潜变量与可微重参数化条件保留。高维边缘似然估计不可靠、全局参数全变分处理未实验，均明确区分于已测试的下界/生成实例。去噪和补全属于作者提出的应用方向，非本文已完成的任务评测。
- GAN 的理想最优与收敛讨论是分布空间条件性分析；p.5 作者明确说明有限参数族的实际优化不受该证明覆盖。Parzen 似然是核估计，方差和高维局限不能被忽略；作者未声称样本优于所有既有方法。
- A3C 部分曲线选最佳运行，而全游戏对照另有固定超参数协议。平均优势不等于每个游戏都胜出；官方补充 p.9 的逐游戏表存在显著失败案例。补充 p.2 指出 MuJoCo 接触模型变化使大多数任务分数不能与所引前作直接比较；不声称普遍实时/硬件效率保证。连续版本不共享策略/价值参数与不自举的设置并未泛化为所有 A3C 配置。
- Transformer 主 fullText 是 11 页正式 PDF，而非 15 页作者 v5。正式 p.8 Table 2 的德语/法语数值为 28.4/41.0；作者 v5 摘要及同表写 28.4/41.8，但该版本同页 §6.1 法语正文仍写 41.0。官方落地摘要还与正式 PDF 存在不同数字，正文导读以实际主 PDF 为准。作者 v5 新增成分句法解析和注意力可视化，正式 PDF 本身并未附其正文提及的附录，均单独记录，不移入正式版本的实验贡献。位置外推只是选择动机；全局注意力二次代价与自回归生成保留。

## 补充材料与版本核对窗口

以下是在主 fullText 之外的额外审核上下文；不冒充六条主记录的 sourcePages。A3C readingAdvice 要求读者核对终止/非终止末端，主论文 p.4 明确指向补充算法 S2，实际终止设置由官方补充 p.4 检查。其余窗口解释补充设置和版本边界；主导读的具体机制与实验断言由主 PDF 的 claimEvidence 支持。

| 辅助文件 / PDF 页 | Unicode start:end | UTF-8 slice SHA-256 | 核对结果 |
|---|---|---|---|
| `a3c-supp.pages.json` / 4 | 518:606 | `74d72fb55b18daf58caa347988772c57eef3d1f63daab54cb8b63bd02e459c41` | 补充算法 S2 在终止末端置回报为零，非终止末端由状态价值自举；用于 readingAdvice 的核对。 |
| `a3c-supp.pages.json` / 2 | 2450:2774 | `868fe2c6e6bbdf77da0cfc7e99727138a516bfe2717b1f49dafacffe944540c1` | MuJoCo 接触模型变化使大多数任务奖励不能与所引前作直接比较；额外评测边界。 |
| `a3c-supp.pages.json` / 2 | 3481:4532 | `c19092e3f78467029655a1d4e1304ad3d24d3e05ee42c7498b2a8a9eb786a9a6` | 连续策略输出高斯参数，连续实验策略与价值不共享参数，整段 episode 更新且不自举；补充版本边界。 |
| `transformer-author-v5.pages.json` / 8 | 640:677 | `e49eace6ed8cc1c03662ffea0c60c58e6b820b0d74dcdc2986d96a38a503cad9` | 作者 v5 Table 2 法语分数为 41.8；同页正文仍为 41.0，不能覆盖正式 PDF 的 41.0。 |
| `transformer-author-v5.pages.json` / 8 | 1413:1508 | `df5196fbcf8f067d9d9e63c275d72a4ad73eccbc3dfd42a4731ad062ecbc61af` | 同一作者 v5 的 §6.1 法语结果正文仍写 41.0；与同页 Table 2 的 41.8 不同，单列上下文避免合并版本数字。 |
| `transformer-author-v5.pages.json` / 9 | 2129:2362 | `af3981253f4d82e7b7e050c948d86923a629ed4aee516da1e3fd1f96ef2bf599` | 作者 v5 新增英语成分句法解析小节；不写入正式版导读的实验贡献。 |
| `transformer-author-v5.pages.json` / 13 | 432:808 | `3e3ed45fb221087e91175acfaeade24b519ffb1c671c6ef373d2501d802bed3b` | 作者 v5 的注意力可视化附录 Figure 3 以 making…more difficult 说明长距离连接；导读不据图宣称普遍语法能力。 |
| `transformer-author-v5.pages.json` / 14 | 546:812 | `240a1ab2b1536b902dd4171010f8828fe0a19a30c7c0731a7b1309ce9a77d9ee` | 作者 v5 Figure 4 讨论 its 相关指代注意力，属于可视化例子。 |
| `transformer-author-v5.pages.json` / 15 | 546:815 | `3372dba967bac22ec3c620eb69aa3dbb70806ab3308c1980bbc9fd3263689b23` | 作者 v5 Figure 5 讨论不同注意力头的结构行为例子。 |

## 本字段门禁与冻结

实际运行 `validate_guides({"AI": dataset}, AI_catalog_rows, as_of=date(2026,10,3), source_root=guide-source-intermediates)`：`ok=true`、`complete=false`、`readyCount=6`、`candidateCount=0`、`fullTextBytesRechecked=6`、`errors=[]`。complete=false 表示本调用仅验收 AI 字段，不是三十篇整体验收。另独立重算两份辅助 PDF/提取 SHA 和实际页树；八份源文件均一致。

正文七区块的字面证据覆盖、每一窗口非空及其原始 Unicode offsets/hash、全页阅读声明、身份/标题/主领域、1–6 顺序和 Han/visible 预算均经门禁。推断性建议以“据此”或“工程上”明示并分类 readerInference。该程序只证明结构、字节与可复查性；不证明作者论证正确或任务外泛化，完整独立审查仍待总流程完成。

当前 `research/classics/AI.json` 及已检查的 AI 经典证据路径相对 bde52ef 锚点无差异。本作者只写 AI 导读 JSON、此审计与 repo 外 AI 中间件；未执行提交、引用更新、推送、部署或产品代码改动。

字段 JSON SHA-256：`00a6ee6fd397a58a8efb5041e63da9972d98253b369f1523d4614ae931ef97f7`。
此审计自己的最终字节哈希在交接消息中报告，避免自引用改变字节。
