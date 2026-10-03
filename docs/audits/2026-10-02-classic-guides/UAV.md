# UAV：六篇完整原文导读字段审计

本次字段审计写于 2026-10-02T04:43:45.112636+00:00。工作区维护曾删除未封存材料；本字段从公开主源重新下载、重新提取、重新通读，没有复用或猜测丢失的哈希。六条 `ready` 表示字段作者按合同完成正文及证据，整个序列仍待新独立审阅，不代替三十篇的最终验收。

## 选择与阅读链

六个 ID 均来自不可修改的已验证 UAV 目录；标题直接取目录规范标题。学习顺序为系统建模与估计 → 几何跟踪 → 光滑多项式规划 → 连续区间避碰 → 旋翼阻力前馈 → 协同载荷运输。Richter 与 Deits 保留已经批准的替代选择，使规划环节有可访问的完整作者原文。没有修改目录或其证据。

| 顺序 | 目录 ID | 实际 PDF 页数 | 概述 Han/可见 | 六节 Han/可见 |
|---|---|---:|---:|---:|
| 1 | `classic:uav:mahony-multirotor-2012` | 13 | 166/180 | 654/698 |
| 2 | `classic:uav:lee-geometric-2010` | 6 | 171/183 | 698/741 |
| 3 | `classic:uav:richter-polynomial-2016` | 16 | 172/184 | 706/754 |
| 4 | `classic:uav:deits-mixed-integer-2015` | 8 | 174/185 | 726/773 |
| 5 | `classic:uav:faessler-rotor-drag-2018` | 22 | 161/174 | 730/776 |
| 6 | `classic:uav:sreenath-cable-manipulation-2013` | 8 | 175/186 | 728/774 |

全部六篇共 73 个 PDF 文件页逐页读取，正文、附录和伴随报告均包含，参考文献已扫描。页码均为一基 PDF 文件索引；印刷标签单独说明。每篇有概述及 problem/method/contribution/applicability/limitations/readingAdvice 六个原创中文段落。

## 实际来源与版本

### 1. Multirotor Aerial Vehicles: Modeling, Estimation, and Control of Quadrotor

- 实际请求 URL：https://www.kostasalexis.com/uploads/5/8/4/4/58449511/ram_paper.pdf
- 检查时间：2026-10-02T04:27:15.680515+00:00；完整字节 1237000；实际页数 13。
- 版本：Kostas Alexis 学术教学站托管的 IEEE Robotics & Automation Magazine 2012 正式排版完整镜像，13 页，对应印刷页 20–32；首页保留 DOI 10.1109/MRA.2012.2206474 及出版信息。实际下载主机为 kostasalexis.com，不是 ANU 受限库。
- PDF SHA-256：`a3af768044aad58759937d625f8a1972147e6ed11e327bbdea4e6980ec469572`
- 全页提取 JSON SHA-256：`19c3734b9c42a29122ffe1856c7e295a61adad9001ac7cdb5f36df23f0141503`
- 重新完整阅读时间：2026-10-02T04:40:39.580184+00:00；页覆盖 `1–13`。
- 实际渲染并查看 PDF 页：3, 7, 8, 9, 10, 11, 12。

### 2. Geometric tracking control of a quadrotor UAV on SE(3)

- 实际请求 URL：https://mleok.science/pdf/LeLeMc2010_quadrotor.pdf
- 检查时间：2026-10-02T04:27:14.844216+00:00；完整字节 508286；实际页数 6。
- 版本：作者 Melvin Leok 当前主页 mleok.science 提供的 IEEE CDC 2010 正式会议排版完整重印，6 页，对应印刷页 5420–5425。只依据该六页版本；正文把证明指向外部 arXiv:1003.2005v1，本导读未下载或混入该外部预印本。
- PDF SHA-256：`a664bdd644e82db8b49ee6005baaeb05879c66ccb128a9a73396407928db1ce5`
- 全页提取 JSON SHA-256：`f6b0b656083be4eeb5461fecfb769d51cbd17b140481cb7102cfe8d5eb21c938`
- 重新完整阅读时间：2026-10-02T04:40:39.580184+00:00；页覆盖 `1–6`。
- 实际渲染并查看 PDF 页：3, 4, 6。

### 3. Polynomial Trajectory Planning for Aggressive Quadrotor Flight in Dense Indoor Environments

- 实际请求 URL：https://groups.csail.mit.edu/rrg/papers/Richter_ISRR13.pdf
- 检查时间：2026-10-02T04:27:20.076739+00:00；完整字节 4680400；实际页数 16。
- 版本：MIT CSAIL 作者组公开的 ISRR 2013 同名论文完整作者稿，16 页，首页明确标注 Proceedings of ISRR 2013；对应目录中 2016 年 Springer 会议集章节身份。不是 2016 出版章节的 649–666 页排版，本导读只依据此作者稿。
- PDF SHA-256：`d9c9bc58820200a05c2f33935befe850b26292ad40edabf303fbf0e0f0ef6876`
- 全页提取 JSON SHA-256：`b8e4be543007411edd9a99e4868456bef255d219b5d94ba640c2a49427e043e8`
- 重新完整阅读时间：2026-10-02T04:40:39.580184+00:00；页覆盖 `1–16`。
- 实际渲染并查看 PDF 页：7, 13, 14。

### 4. Efficient mixed-integer planning for UAVs in cluttered environments

- 实际请求 URL：https://dspace.mit.edu/server/api/core/bitstreams/8fae8516-d702-4f80-aa12-17fba60e5202/content
- 检查时间：2026-10-02T04:27:22.268596+00:00；完整字节 804133；实际页数 8。
- 版本：MIT DSpace 标记为 Author’s final manuscript 的 ICRA 2015 同名论文完整作者定稿，8 页；从机构公开 bitstream API 下载，实际重定向至 cf003.cdn.4science.cloud 机构资产主机。无出版社页码页眉，不冒称 IEEE 42–49 页正式排版。
- PDF SHA-256：`199aee8022607e7191b720cd03ec61b75b7fff1ef225aa42566d1d5666d2f2ac`
- 全页提取 JSON SHA-256：`bba060dcf488f230cad0f639ffa6fc149b5e4b6881f728e3c3535757c7939902`
- 重新完整阅读时间：2026-10-02T04:40:39.580184+00:00；页覆盖 `1–8`。
- 实际渲染并查看 PDF 页：4, 6, 7。

### 5. Differential Flatness of Quadrotor Dynamics Subject to Rotor Drag for Accurate Tracking of High-Speed Trajectories

- 实际请求 URL：https://rpg.ifi.uzh.ch/docs/RAL18_Faessler.pdf
- 检查时间：2026-10-02T04:27:22.300950+00:00；完整字节 3749904；实际页数 22。
- 版本：苏黎世大学作者研究组 rpg.ifi.uzh.ch 公开的合并文件，22 页：PDF 页 1–7 为 RA-L 同名论文作者版主文，PDF 页 8–22 为另题 Detailed Derivations of… 的十五页伴随技术报告（报告印刷页 1–15，含附录）。主文对应 2018 RA-L 正式身份；不是一篇 22 页的正式 RA-L 排版文章。
- PDF SHA-256：`d8e562951e4369c474c176c70f1b9135c56c90e58da3912dd824c390c39bd862`
- 全页提取 JSON SHA-256：`c40f965ea31597cf55b1c334c640bf5de71d94b9f0320fe039470035e20b113e`
- 重新完整阅读时间：2026-10-02T04:40:39.580184+00:00；页覆盖 `1–22`。
- 实际渲染并查看 PDF 页：2, 3, 4, 6, 19, 21。

### 6. Dynamics, Control and Planning for Cooperative Manipulation of Payloads Suspended by Cables from Multiple Quadrotor Robots

- 实际请求 URL：https://www.roboticsproceedings.org/rss09/p11.pdf
- 检查时间：2026-10-02T04:27:18.568232+00:00；完整字节 942900；实际页数 8。
- 版本：Robotics: Science and Systems IX 2013 官方论文集完整 PDF，8 页，包含点质量、刚体和多架四旋翼协同载荷模型。与目录 DOI 10.15607/RSS.2013.IX.011 一致；不是另篇单架四旋翼吊载论文。
- PDF SHA-256：`64ccea36b6b598966039238e92d32372881493e4d683514d404f96b282433f22`
- 全页提取 JSON SHA-256：`0c4d2b718f15997bddff06387b03b3c6fe3ced83e597c9c817c6fd784d65ce89`
- 重新完整阅读时间：2026-10-02T04:40:39.580184+00:00；页覆盖 `1–8`。
- 实际渲染并查看 PDF 页：3, 5, 8。

MIT DSpace 的 Deits 条目公开标记 Author's final manuscript（机构条目： https://dspace.mit.edu/entities/publication/1f96e828-27bd-4a5a-9bfe-9cb3cfd250ee ）。下载从稳定 bitstream API 发起，响应实际重定向到 `cf003.cdn.4science.cloud` 的 MIT 资产；完整最终重定向 URL 与时间保留在仓库外 retrieval JSON，未把短期签名地址当作长期书目地址。Lee 的现作者页面 https://mleok.science/LeLeMc2010_quadrotor.html 链到本次使用的六页重印。

## 公式、实验与适用边界

- Mahony 是系统教程，静态旋翼推力、前飞集总气动、低频近悬停加速度近似与电机/姿态/位置嵌套环均沿实际正文阅读。水平速度观测还假定近似恒高和可靠姿态；没有写成任意激烈机动下的通用重力测量或速度保证。
- Lee 使用六页 CDC 正式重印。正文第 3 页将证明指向外部 reference [20]；没有以 arXiv:1003.2005 的另一版本或其他论文补写本版证明。姿态指数稳定、完整系统指数稳定与较大姿态误差时的指数吸引性已分开，初值/角速度/增益限制保留。第 6 页 Figure 4–5 为数值结果，逐旋翼推力含负值；普通硬件饱和可行性属于不能据此推出的读者判断。
- Richter 的 2013 作者稿与 2016 目录章节年份分别声明。第 13 页 Tables 2–3 的收益是数值稳定性，不能一概写成比约束形式更快。第 14 页实机使用预建 OctoMap 和机载估计控制；没有扩大成未知环境在线建图避障。固定时间端点变量二次最优与外层时间迭代/路径选择的全局最优性分开。
- Deits 从整个区间的半空间非负条件推导平方和与三次曲线锥约束；区域分配先求低阶曲线，固定分配后求高阶光滑解。所谓最优只针对单段位于单凸区域的受限集合。第 6–7 页为二维/三维仿真，第 8 页把实机执行列作未来工作，未声称硬件实时重规划已经验证。
- Faessler 的质量归一化总推力单位为加速度；D 为质量归一化旋翼阻力的机体系对角系数，速度先映入机体系再旋回世界系；body rates 为机体系角速度，区别于欧拉角导数。主文第 4 页 equation (39) 定义 RMS 位置误差，第 6 页 Table I 十圈圆形测试 Ea 为无阻力 17.53 cm、圆形辨识系数 6.54 cm，未将其推广为任意轨迹的固定改善比例。实验使用 OptiTrack 状态，辨识隔离效应时固定 dz/kh；模型的无风、刚性桨和推力无关阻力假设保留。PDF 第 18–20 页伴随报告讨论奇异情形、倒置跳变及短时补救，不能视作全球连续重建保证；第 21–22 页附录的坐标求导警示归于伴随报告。
- Sreenath 是多机协作 RSS 2013 论文，不是单机吊载论文。点质量和刚体模型、缆绳方向坐标系、载荷合力与零空间内部力分别阅读。第 4 页 Remark 6 的两机刚体秩不足和第 5 页 Theorem 2 写出的机数多于三条件及三机松一绳反例保留；不推断任意数量连续松绳均保持刚体平坦性。实机三机实验以 Vicon 飞行器状态反馈，载荷位置仅作评估；载荷反馈仍是未来工作。原文“300%–400% lower”含混，正文仅陈述图中的误差大小关系，没有复述该百分比。

## 证据与验证

全页提取采用 PyMuPDF `Page.get_text("text", sort=False)` 的 PDF 内容流顺序，保留完整 Unicode 页字符串，提取方法及运行版本写入每份 `.pages.json`。两栏顺序、被打散的公式、表格与图已通过实际页面渲染核对。上述 25 个渲染页面及读取日志留在仓库外。

291 条 `claimEvidence` 覆盖六篇概述与所有六节。每条 claim 是相应中文正文的字面子串；页段以真实标题/段首界定，offset 对精确提取 Unicode 字符串取值，SHA-256 对 UTF-8 切片计算，不重新归一化。跨页或多环节句使用多条同字面 claim 的互补页段证据，单条只覆盖该句在对应页的相关部分。工程适用建议、阅读顺序及从验证范围推出的限制明确以“工程上”“据此”标记为 readerInference；没有把它们写成作者实验证明。

本次已调用实际 `validate_guides({"UAV": dataset}, UAV_catalog_rows, as_of=date(2026,10,2), source_root=guide_source_intermediates, require_complete=False)`。结果：`ok=true`、`complete=false`、`readyCount=6`、`candidateCount=0`、`fullTextBytesRechecked=6`、`errors=[]`。`complete=false` 是仅验证本字段的真实结果，不宣称三十篇已经齐备。机器报告存仓库外 `UAV/gate-report.json`。

所有第三方完整 PDF、全页文本、渲染图片、下载/阅读日志与生成辅助脚本均留在 `/workspace/scratch/7877d1c29d91/guide-source-intermediates/UAV/`。仓库仅新增本字段原创 JSON 与本审计；不包含第三方完整作品。没有提交、推送、合并、部署或修改生产文件。独立全字段内容审阅与最终序列验收由根任务继续执行。
