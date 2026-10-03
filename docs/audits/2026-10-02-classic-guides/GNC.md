# GNC 全文导读审计（2026-10-02）

状态：本领域六篇完成作者自检并通过稀疏领域 gate，等待主任务独立审查；本记录不宣告全体30篇验收。目录身份、标题及主领域均来自既有已验证GNC目录，未修改目录及原证据。维护清除未封存工作后，六份PDF已重新从公开来源获取、重新提取和逐页阅读；不声称丢失的第四阶段文件已恢复。

## 选择与完整阅读范围

| 顺序 | 子领域 | 已验证目录ID | 实际PDF页数 | 已读PDF页索引 |
|---|---|---|---:|---|
| 1 | 导航 | `classic:gnc:kalman1960` | 8 | 1–8 |
| 2 | 导航 | `classic:gnc:barrau2017` | 36 | 1–36 |
| 3 | 制导 | `classic:gnc:coulter1992` | 15 | 1–15 |
| 4 | 制导 | `classic:gnc:breivik2005` | 8 | 1–8 |
| 5 | 控制 | `classic:gnc:ziegler1942` | 7 | 1–7 |
| 6 | 控制 | `classic:gnc:brockett1983` | 11 | 1–11 |

导航、制导、控制各两篇，学习顺序唯一且为1–6。共85个实际PDF页面，正文及所用版本附录全部阅读，参考文献扫描；Coulter的四个空白背页及Kalman的编辑材料也已查看。页码采用PDF的一基索引，版面印刷页码只作为定位补充。最终复核时间：`2026-10-02T04:45:56.448945+00:00`。

- Kalman：NTNU公开的IEEE Press选集原论文影印重印，共8个双页扫描页。原论文从PDF3右半开始，至PDF8结束，选集印刷169–179对应原刊35–45，概率附录也已读。PDF1书目、PDF2及PDF3左半编辑评论和前篇残页不作为原论文技术证据；PDF3证据上下文的起点位于原论文标题之后。没有选用Duke的John Lukesh手工Word/OCR重制版。
- Barrau：完整arXiv:1410.1465v4作者预印本，文件标注2015-10-19；对应目录2017年TAC论文，明确非出版社版式。36页中的附录A–D、文献及末尾图均已读。
- Coulter：CMU-RI-TR-92-01完整报告扫描，共15个PDF页面；封面、目录、图目、摘要和四个空白背页保留，正文印刷3–9，末页参考文献已扫描。
- Breivik：Fossen作者公开出版物目录的完整CDC2005预印本，8页含正文、证明与参考文献；对应正式会议印刷627–634，明确非出版社版式。
- Ziegler–Nichols：Walter Driedger获ASME许可制作的完整论文正文OCR/Word重建版，Di Ruscio教学站镜像，7页对应印刷759–765，包含表1、总结与结论；非原页影印。原刊另外列出的766–768页讨论及作者闭幕意见不在此文件内，不将其计入已读正文，也没有借其支撑导读。授权说明见实际PDF页脚。
- Brockett：Harvard Robotics Laboratory公开的作者论文扫描，11页对应印刷181–191，证明、例子、致谢和文献均已读。原OCR识别较差，11页全部实际渲染并逐页查看，公式和定理依据图像核对。

## 来源与字节绑定

| 目录ID | 本次实际完整PDF地址 | 本次实际获取时间（UTC） |
|---|---|---|
| `classic:gnc:kalman1960` | [实际完整PDF](https://skoge.folk.ntnu.no/puublications_others/1960_Kalman%20-%20A%20new%20approach%20to%20linear%20filtering%20and%20prediction%20problems%20-%20Orinal%20version%20with%20comments.pdf) | `2026-10-02T04:27:38.918200+00:00` |
| `classic:gnc:barrau2017` | [实际完整PDF](https://arxiv.org/pdf/1410.1465v4) | `2026-10-02T04:27:39.064745+00:00` |
| `classic:gnc:coulter1992` | [实际完整PDF](https://publications.ri.cmu.edu/storage/publications/pub_files/pub3/coulter_r_craig_1992_1/coulter_r_craig_1992_1.pdf) | `2026-10-02T04:27:41.097953+00:00` |
| `classic:gnc:breivik2005` | [实际完整PDF](https://www.fossen.biz/publications/2005%20Breivik%20and%20Fossen%20CDC.pdf) | `2026-10-02T04:27:36.937802+00:00` |
| `classic:gnc:ziegler1942` | [实际完整PDF](https://davidr.no/iiav3017/papers/Ziegler_Nichols_%201942.pdf) | `2026-10-02T04:27:36.448891+00:00` |
| `classic:gnc:brockett1983` | [实际完整PDF](https://hrl.harvard.edu/publications/brockett83asymptotic.pdf) | `2026-10-02T04:27:35.881439+00:00` |

- `classic:gnc:kalman1960`：PDF `f38a0e48c2a44e1feeb7675b5cd51a674a88eac264ba893aa41a55705d49f1b7`；页提取JSON `9fd1e3c2eebddeafa752561fccfe6477d3a634712b99b0e7de7effd8ceeb44e6`。
- `classic:gnc:barrau2017`：PDF `ca81b8ef0fc135e6d67a9531f30188476a2d927ee47a95e83d0f9da4f8a91e37`；页提取JSON `c63664d64f864bb79994992840426468e7f907a7d30f01e39c2314a7dcd55cfb`。
- `classic:gnc:coulter1992`：PDF `65fd5c95c5a4a452bef39003966559b633656ac3e3ec11d3c1a85a6469841141`；页提取JSON `5f985f7551c016d564621fd3da5250b710f860084a80ebaf4af1158386a7da6e`。
- `classic:gnc:breivik2005`：PDF `566d45204cf1bce786dc86431aae8fbf9ebeaaa9a3ba962e89e63d79e0410b5f`；页提取JSON `ff017f6de8206861ade40188df806aa978b7c7a106ab0a5479758eb796e8c305`。
- `classic:gnc:ziegler1942`：PDF `2834f3507113b995721f815465a478731aba1a7baae7304d463d909dfa39df9c`；页提取JSON `33f15c9f60eecde67241f1511c001c8840f28068ef0377701b7afed5024f91dc`。
- `classic:gnc:brockett1983`：PDF `9f9df3a82645bf705960560247be5feaa57f065120921677c207149f81aba8df`；页提取JSON `6c00b37574c784bb848dfb8b13fc44e82cf9d6d20f9fbff76d0e8ec10d27b7e3`。

六份PDF、逐页提取JSON及渲染图均位于仓库外 `guide-source-intermediates/GNC/`。Kalman使用2.3倍实际渲染的左右半页Tesseract英文OCR，按左后右原样串接，保留全部页；其余使用PyMuPDF原生文本块顺序提取，不归一化原字符串。页提取JSON具有实际PDF哈希绑定，包含每个PDF页的原始实际文本。审计及导读不包含第三方整篇正文或整篇渲染。

## 版面和技术复核

Kalman查看全部8个双页版面，并额外查看PDF6右半递推增益/协方差与稳定性备注、PDF7左半对偶表、PDF8右半概率附录。Barrau查看PDF7与13的对数线性性质及稳定性定理，以及PDF35–36仿真图。Coulter查看PDF11–12几何推导及坐标轴、PDF14–15参数与动力学限制，并核对PDF2、4、6、8为空白。Breivik查看PDF3–4及6–7的几何式、李雅普诺夫论证、稳定性命题和速度界讨论。Ziegler–Nichols查看PDF5–7的反应曲线、整定总结、表1及结论。Brockett查看全部PDF1–11。

复核保留以下具体边界，正文及对应证据已经体现：

- Kalman区分高斯条件下的估计结论与非高斯线性估计类内平方损失最优；作者在本文未证明滤波稳定性。
- Barrau的精确对数线性结论是误差传播性质；完整观察器收敛为指定条件下的局部结论。确定性分析不等于任意噪声下随机最优性。
- Coulter的横向坐标按原图解释；路径记录的距离是到路径起点的直线距离。前视距离影响回归路径与弯道跟踪，曲率执行的动力学假定与几何推导分开说明。
- Breivik的基础对象是理想速度受控粒子；一致全局渐近和局部指数性质保留相应假设。特殊全局指数速度律可能无界，作者明确承认真实载体的速度上限。
- Ziegler–Nichols按原文灵敏度、复位速率和预作用时间的定义理解参数；表1是动作、度量和单位的整理，不是性能对比实验表。经验整定不被描述为任意过程的严格最优解。
- Brockett的障碍限于所述局部连续可微静态状态反馈类别；必要的开集覆盖条件不被写成一般充分条件，也不被扩大为所有控制方式或全局初值的绝对不可能。

## 中文篇幅与逐条证据

| 目录ID | 概述：Han / 可见字符 | 六段合计：Han / 可见字符 | 证据条数 |
|---|---:|---:|---:|
| `classic:gnc:kalman1960` | 182 / 195 | 602 / 647 | 17 |
| `classic:gnc:barrau2017` | 183 / 196 | 614 / 658 | 17 |
| `classic:gnc:coulter1992` | 174 / 186 | 647 / 697 | 17 |
| `classic:gnc:breivik2005` | 185 / 196 | 659 / 704 | 17 |
| `classic:gnc:ziegler1942` | 175 / 189 | 682 / 730 | 18 |
| `classic:gnc:brockett1983` | 181 / 195 | 676 / 716 | 17 |

各篇概述及问题、方法、贡献、适用性、局限、阅读建议七个正文位置均有支持，共103条证据。证据的claim是相应正文的精确字面子串；paperFact与readerInference分开，后者明确使用“据此”“工程上”或“推断”，共30条。每条绑定实际PDF页索引、实际章节/定理/图表定位以及实际提取文本的Unicode切片起止与UTF-8 SHA-256。Brockett的差OCR使部分上下文保留完整单页切片，但定位到对应引言、定理、定义或引理，内容以实际页图核对。没有将提取质量低的公式转录成导读中的数值公式。

## 最终领域验证与冻结

在最终复核时间写入后，使用 `scripts/classic_guides.py` 的实际 `validate_guides` 接口，对GNC数据和GNC目录运行普通稀疏领域核验：`ok=true`、`readyCount=6`、`candidateCount=0`、`domainCounts.GNC=6`、`errors=[]`、`fullTextBytesRechecked=6`。另外使用PyMuPDF重新读取各PDF实际页树并确认8/36/15/8/7/11页，与声明一致。全部PDF字节哈希及提取JSON字节哈希重新计算一致。

不传source_root的声明核验也为 `ok=true`、`readyCount=6`、`errors=[]`，并明确 `fullTextBytesRechecked=0`。两个领域运行的 `complete=false` 是其他领域未传入的正常稀疏状态，不作为全体30篇严格核验。实际完整输出保存在仓库外 `GNC/gate-report.json` 与 `GNC/declaration-gate-report.json`，供主任务复核。

冻结的 `research/classic-guides/GNC.json` SHA-256：`ca3b40363a9809c5ea828e86f3902beba86302d58cfd5d1579533aedc1c59984`。本审计文件的实际SHA-256及所有来源绑定另存仓库外 `GNC/freeze-manifest.json`，避免自引用哈希。仅写入本领域JSON和本审计，未执行Git提交、推送、合并或部署；全体验收及独立审查由主任务继续。
