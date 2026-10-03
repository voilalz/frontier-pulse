# SLAM 全文导读字段审计（重新取得原文后的当前交付）

审计冻结时间：2026-10-02T04:42:17.967834+00:00。目录身份取当前已恢复的 verified SLAM 目录，目录截至日仍为 2026-10-01；导读验收截至日为 2026-10-02。

此前未封存的第四序列工作和原始中间文件在维护中丢失。本次六篇原文均重新下载为完整 PDF，重新提取全部页面、逐页阅读并重新绑定正文证据；没有声称恢复旧 JSON、旧审计或旧审核结果。本文件所列时间与哈希全部由本次实际文件计算。

学习顺序为 FastSLAM → iSAM2 → ORB-SLAM → DSO → LOAM → LIO-SAM：先理解条件独立分解，再理解增量图优化后端，继而比较单目特征系统与直接里程计，最后进入激光双时间尺度分工和激光惯性因子图。顺序是读者的学习组织，不声称六篇具有逐篇继承关系。六个身份均是现有 verified SLAM 项，未修改目录、bibliographic/classic evidence 或其原始截至日。

## 本次完整阅读与版式核查

全部 77 个 PDF 页面按一基索引重读，所有参考文献页均扫描。iSAM2 第19页附录A是多媒体扩展索引，已读；ORB-SLAM 第16—17页非线性优化附录完整阅读，参考文献至第18页。所取得的 FastSLAM、DSO v2、LOAM、LIO-SAM v3 文件没有额外文字附录。DSO 文中指向原始跟踪数据/绘图脚本和演示视频，LIO-SAM 指向演示视频；这些外部数据/视频未被冒充为已读论文附录，也未用于正文细节。

使用 PyMuPDF Page.get_text("text", sort=False) 原样提取，全部页包含在 pages.json；不清洗、不归一化、不替换连字或错误符号。FastSLAM 数学符号字体提取会出现控制字符，公式以渲染原页核对，不把错码伪装修复文本。所有上下文索引是原始 Unicode 字符区间，SHA-256 对准确区间的 UTF-8 字节计算。

已实际查看 34 个关键渲染页（1.7倍矩阵、两页拼接 PNG、original detail）：

- fastslam：PDF页 2, 3, 4, 5, 6。
- isam2：PDF页 4, 8, 9, 10, 14, 16。
- orbslam：PDF页 4, 6, 7, 9, 16, 17。
- dso：PDF页 4, 5, 6, 7, 13, 14。
- loam：PDF页 3, 4, 5, 6, 8。
- liosam：PDF页 2, 3, 4, 5, 6, 7。

渲染核对覆盖 FastSLAM 后验分解/采样/树共享图；iSAM2 因子图、信息矩阵、贝叶斯树、更新算法与时间/误差表；ORB-SLAM 线程、初始化、回环和附录残差；DSO 光度模型、因子图、雅可比、舒尔补与参数/噪声图；LOAM 特征、距离残差、时间插值与地图变换；LIO-SAM 系统因子图、预积分、局部地图和实验表。正文不复刻未经确认的公式，也不引用当前未核实的在线排行榜。

## 字符预算与证据覆盖

计数按门禁 text_counts，Han 为汉字数，visible 为去空白 Unicode 字符数。标题、元数据及证据不计入正文。每个概述与六个正文章节的所有完整句子均有证据；跨页综合句另外绑定相应页内上下文，同一句重复绑定不同支持页是有意的。读者建议及工程推断以“工程上”或“据此”明确标注为 readerInference。

| 顺序 / 身份 | PDF页 | 概述 Han / visible | 六段 Han / visible | 证据条目 |
|---|---:|---:|---:|---:|
| 1 / classic:slam:fastslam | 6 | 156 / 165 | 589 / 627 | 25 |
| 2 / classic:slam:isam2 | 19 | 160 / 170 | 594 / 633 | 26 |
| 3 / classic:slam:orbslam | 18 | 165 / 178 | 595 / 644 | 23 |
| 4 / classic:slam:dso | 17 | 160 / 172 | 603 / 649 | 27 |
| 5 / classic:slam:loam | 9 | 167 / 176 | 617 / 660 | 25 |
| 6 / classic:slam:liosam | 8 | 158 / 168 | 609 / 655 | 28 |

合计 77 页，154 条证据。六个概述均 ≥150 Han 且 ≤220 visible，六段合计均 ≥500 Han 且 ≤800 visible。

## 逐篇原文身份与实际字节记录

### classic:slam:fastslam

目录正式身份：FastSLAM: A Factored Solution to the Simultaneous Localization and Mapping Problem。

- 实际 PDF URL：https://robots.stanford.edu/papers/montemerlo.fastslam-tr.pdf
- 取得时间：2026-10-02T04:26:33.941548+00:00
- 全文复核时间：2026-10-02T04:39:56.935842+00:00
- 完整 PDF 页数：6；已读页：1—6（PDF索引，不混用印刷页码）。
- 版次：作者提供的六页 AAAI 2002 同名论文稿；未混入 2003 FastSLAM 2.0 的观测引导提议分布或结果。
- 完整 PDF SHA-256：`805ad93bafae89cdf78592707dc006680c81e0bbb827cce6b1690fb9e640f29e`
- 提取文件：`SLAM/fastslam.pages.json`；提取 JSON SHA-256：`2a6ed112740e81afed04665b4245ec9ad1d65ae672da7f634cfdfacb82433cb9`
- 实际提取方法：PyMuPDF 1.26.6 Page.get_text("text", sort=False); exact Unicode, no normalization

### classic:slam:isam2

目录正式身份：iSAM2: Incremental smoothing and mapping using the Bayes tree。

- 实际 PDF URL：https://www.cs.cmu.edu/~kaess/pub/Kaess12ijrr.pdf
- 取得时间：2026-10-02T04:26:32.976262+00:00
- 全文复核时间：2026-10-02T04:39:56.935842+00:00
- 完整 PDF 页数：19；已读页：1—19（PDF索引，不混用印刷页码）。
- 版次：作者站点 Kaess12ijrr.pdf，PDF首页明示 Draft manuscript, April 6, 2011. Submitted to IJRR.；这是对应目录2012 IJRR论文的2011投稿草稿，非最终期刊排版版；附录A为多媒体索引。
- 完整 PDF SHA-256：`52c917e56d338afbb388462053850ff735ddadf48831c59ec8c5418448e5c790`
- 提取文件：`SLAM/isam2.pages.json`；提取 JSON SHA-256：`74b69cbf3e8a2ceb0446b0fb9255ecf503ca6ec321d4f1485d52f2ba65efbd55`
- 实际提取方法：PyMuPDF 1.26.6 Page.get_text("text", sort=False); exact Unicode, no normalization

### classic:slam:orbslam

目录正式身份：ORB-SLAM: A Versatile and Accurate Monocular SLAM System。

- 实际 PDF URL：https://arxiv.org/pdf/1502.00956
- 取得时间：2026-10-02T04:26:33.431971+00:00
- 全文复核时间：2026-10-02T04:39:56.935842+00:00
- 完整 PDF 页数：18；已读页：1—18（PDF索引，不混用印刷页码）。
- 版次：arXiv:1502.00956v2，2015-09-18；TRO已接收作者稿，额外版权/接收封面为PDF页1，PDF页2对应印刷页1；含非线性优化附录；仅原始单目ORB-SLAM，不混入ORB-SLAM2/3能力。
- 完整 PDF SHA-256：`442bcef21b04c007628c452e21b3122296e76fee727b1fc766e7d2b666ec3634`
- 提取文件：`SLAM/orbslam.pages.json`；提取 JSON SHA-256：`e2e8a379406717976fc2a9248bdf7433c361ae1605f600be0a47eccb3b066781`
- 实际提取方法：PyMuPDF 1.26.6 Page.get_text("text", sort=False); exact Unicode, no normalization

### classic:slam:dso

目录正式身份：Direct Sparse Odometry。

- 实际 PDF URL：https://arxiv.org/pdf/1607.02565
- 取得时间：2026-10-02T04:26:33.604791+00:00
- 全文复核时间：2026-10-02T04:39:56.935842+00:00
- 完整 PDF 页数：17；已读页：1—17（PDF索引，不混用印刷页码）。
- 版次：arXiv:1607.02565v2，2016-10-07，17页作者预印本；对应目录2018 TPAMI论文身份，但不是最终期刊排版版；仅转述该v2中的模型和实验。
- 完整 PDF SHA-256：`cd85260a38b0b5d0e82c85c37c3540c498a953e39a501d9af5192a35b8284223`
- 提取文件：`SLAM/dso.pages.json`；提取 JSON SHA-256：`ecb77169e4b96a15c6c2df8b50ba4e109bccd7a3bcb365f766c13a3961ac90c8`
- 实际提取方法：PyMuPDF 1.26.6 Page.get_text("text", sort=False); exact Unicode, no normalization

### classic:slam:loam

目录正式身份：LOAM: Lidar Odometry and Mapping in Real-time。

- 实际 PDF URL：https://www.roboticsproceedings.org/rss10/p07.pdf
- 取得时间：2026-10-02T04:26:33.307538+00:00
- 全文复核时间：2026-10-02T04:39:56.935842+00:00
- 完整 PDF 页数：9；已读页：1—9（PDF索引，不混用印刷页码）。
- 版次：Robotics: Science and Systems X官方2014论文p07，9页；仅该LOAM会议版，不混入2017 Low-drift and Real-time Lidar Odometry and Mapping扩展论文或后来回环系统。
- 完整 PDF SHA-256：`0d66f17eadd7770e5894df92a3ca854a9a53f366f2aec6a828eb1bbcd6e28941`
- 提取文件：`SLAM/loam.pages.json`；提取 JSON SHA-256：`9468c79c1a434c8de6dcd649c05275f97d9059ec738c9a6b5d5dc8190b92e43b`
- 实际提取方法：PyMuPDF 1.26.6 Page.get_text("text", sort=False); exact Unicode, no normalization

### classic:slam:liosam

目录正式身份：LIO-SAM: Tightly-coupled Lidar Inertial Odometry via Smoothing and Mapping。

- 实际 PDF URL：https://arxiv.org/pdf/2007.00258
- 取得时间：2026-10-02T04:26:33.435410+00:00
- 全文复核时间：2026-10-02T04:39:56.935842+00:00
- 完整 PDF 页数：8；已读页：1—8（PDF索引，不混用印刷页码）。
- 版次：arXiv:2007.00258v3，2020-07-14，8页IROS同名作者预印本；只引用v3正文。页5表I与Rotation/Walking段落的最大旋转速度互换，全部不采用；页4式12疑似变换记号问题，不转述公式。
- 完整 PDF SHA-256：`8ad11438fc0849de88b1604932f8bfd2732aee640aaf5fb41974b34f555c86f6`
- 提取文件：`SLAM/liosam.pages.json`；提取 JSON SHA-256：`09fb7bde8386df49fb4b33ce73ec491ec4bec28d7dd9c76531f299f6252bc69d`
- 实际提取方法：PyMuPDF 1.26.6 Page.get_text("text", sort=False); exact Unicode, no normalization

## 逐篇范围限制与技术复核结论

- FastSLAM：精确后验分解与有限粒子、观测线性化近似分开陈述；树复杂度依赖地标定位和共享分支组织。正文未把有限示例粒子数或实物局部试验当作普遍保证，未引入 FastSLAM 2.0 的方法或实验。
- iSAM2：2011年4月6日作者投稿草稿的身份已在 fullText.edition 明示；目录保持2012 IJRR同名身份。未把周期性批处理替代写成固定最坏运行时间，也未把拟合最小二乘解的归一化误差当作物理轨迹真值。表1逐数据集时间并非iSAM2全胜，正文明确限定。
- ORB-SLAM：采用带封面的2015 v2已接收作者稿，定位均为PDF页。保持原始单目方法，不借用双目/RGB-D/惯性扩展能力。轨迹比较需尺度对齐；低视差歧义会延迟/拒绝初始化，高速公路及反向校园回环有失败边界。
- DSO：仅2016 v2的模型和评测，未挪用最终2018期刊版新增结果。读完光度模型、首次估计雅可比和边缘化细节；重现式子不是本导读目标。明确其为里程计，并说明ORB-SLAM对比关闭显式回环与重定位。TUM-monoVO、EuRoC图像流、ICL-NUIM均不代表通用设备或无条件优劣。
- LOAM：官方2014 RSS会议版，不是2017扩展文。无回环、基础单轮匀速近似、可选IMU预处理均明确；没有把辅助IMU说成联合估计惯性偏置。局部点云距离、回到起点的偏差与KITTI运动漂移是不同评价；未引用现时排名。
- LIO-SAM：仅2020 v3。表I与Rotation/Walking正文对两项最大旋转速度写反，本导读全部省去这些速度；式12变换记号存在疑问，正文不转述其公式、不自行修正后冒充原文。文中Park相对GPS的RMSE排除了z轴，正文明确；端点闭合误差不被解释为全程三维真值精度。回环示例按欧氏邻域检索，不冒充Scan Context；无人机测试仍是未来工作。其参考文献中的LOAM基准是2017扩展文，不能迁移为本字段2014 LOAM原稿的相同实验。

## 当前字段验收与冻结

本次调用 validate_guides({"SLAM": dataset}, flat_catalog, as_of=date(2026,10,2), source_root=/workspace/scratch/7877d1c29d91/guide-source-intermediates)。按实际原文重检 PDF头/整文件哈希、提取JSON哈希/PDF绑定/页序，以及全部Unicode上下文区间和UTF-8哈希。

- `ok=true`；`readyCount=6`；`candidateCount=0`；`errors=[]`。
- 六条记录全部 `eligible=true` 且 `fullTextBytesRechecked=true`；报告合计实际重检原文6份。
- `complete=false` 是仅载入SLAM的稀疏字段报告，不能据此声称五领域30篇全局完成。
- 当前 JSON SHA-256：`e5df3fdd4e185d4d0814d1370062f161d3f121fefd9e742b0755c12d93b8bd33`。
- 字段报告在仓库外 `SLAM/field-validation.json`；冻结清单在仓库外 `SLAM/freeze.json`。

本字段内容编写者的自检已完成；独立逐篇内容复查及全局严格验收由根任务另行执行，当前冻结不是独立复查已接受的声明。任何重要修正应重跑字段实源门禁并重新冻结。完整第三方PDF、提取文本、图页及生成/审计脚本均仅在仓库外；仓库中只写所属SLAM.json和本审计，无目录、发布、生产或Git引用操作。
