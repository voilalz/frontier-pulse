# CV 六篇全文导读审计

字段自查冻结时间：2026-10-03T08:07:07.641443+00:00。本字段已完成原文阅读、版面核验、中文导读和本地来源门禁；整个三十篇集合的独立内容验收仍由主流程执行。维护前未封存成果没有被宣称恢复；本次 PDF/提取于 2026-10-02 实际重新取得，文件保留后于 2026-10-03 完成未结束的证据绑定与复核。

## 身份、版本与完整阅读

学习顺序为 SIFT → HOG → AlexNet → ResNet → Faster R-CNN → U-Net。六个 ID 均来自不变的已验证 CV 目录；没有改动目录或旧证据字节。下列页数与阅读范围均为一基 PDF 文件页索引，不能与正式印刷页码混用。

|顺序|目录 ID|实际版次|主文页数/已读范围|
|---|---|---|---|
|1|`classic:cv:sift`|作者网站的 2004-01-05 IJCV 已接收稿，文件 28 页；不是期刊 pp.91–110 的排版版。|28 / 1–28|
|2|`classic:cv:hog`|合作者 INRIA 网站的 CVPR 2005 会议作者稿，文件与内部页码 1–8；不是后续技术报告。|8 / 1–8|
|3|`classic:cv:alexnet`|NeurIPS/NIPS 2012 正式会议论文 PDF，文件内部页码 1–9；采用 PDF 正文而非内容不同的网页摘要。另检阅官方补充定性图包。|9 / 1–9|
|4|`classic:cv:resnet`|CVF 开放的 CVPR 2016 正式会议版，文件 9 页，印刷页码 770–778；另完整检阅官方 4 页 Supplementary Materials。|9 / 1–9|
|5|`classic:cv:faster-rcnn`|NeurIPS/NIPS 2015 正式会议版，文件内部页码 1–9；另完整检阅官方 ZIP 内 2 页补充 PDF。不是后来扩展的 arXiv/TPAMI 版。|9 / 1–9|
|6|`classic:cv:unet`|Springer MICCAI 2015 Part III, LNCS 9351 正式章节，文件 8 页，印刷页码 234–241；不是 arXiv 版。|8 / 1–8|

主文共 71 页逐页阅读；参考文献已扫描（SIFT 文件 pp.26–28，HOG p.8，AlexNet p.9，ResNet p.9，Faster R-CNN p.9，U-Net p.8）。ResNet 官方补充 PDF 4 页、Faster R-CNN 官方补充 PDF 2 页全部阅读。AlexNet 官方 ZIP 的 3 份说明与全部 27 张定性图已检阅（8 个特征激活图、11 个预测图、8 个检索图）。

## 主文文件、提取绑定与实际时间

外部来源根目录：`/workspace/scratch/7877d1c29d91/guide-source-intermediates/`。完整第三方 PDF、逐页全文提取、ZIP、视频与渲染均只在仓库外；仓库记录原创中文、事实元数据、短定位及散列。

### Distinctive Image Features from Scale-Invariant Keypoints

- URL：https://www.cs.ubc.ca/~lowe/papers/ijcv04.pdf
- PDF：`CV/sift2004.pdf`，SHA-256 `06f8acc68583e8b7a041d1fda84db83283e49f6cedc4638ea5cdd2f61caf8e3e`。
- 提取：`CV/sift2004.pages.json`，SHA-256 `1ef4fe7ba81adc93893cb0787c664e3eb7fc8c0dba5f6ab619d07e18538b2126`。
- 实际获取：2026-10-02T04:26:46.581633+00:00；完整阅读后复核：2026-10-03T08:07:07.008373+00:00。

### Histograms of Oriented Gradients for Human Detection

- URL：https://lear.inrialpes.fr/people/triggs/pubs/Dalal-cvpr05.pdf
- PDF：`CV/hog2005.pdf`，SHA-256 `eb2bad4bc1e30c9a467a135100ba2be4d12fd8736675af0268e98ebd179c46f0`。
- 提取：`CV/hog2005.pages.json`，SHA-256 `f4aff6f88efbc50c307255f58aa40e413eb71112ffdab68f17bbb78aaa90d23b`。
- 实际获取：2026-10-02T04:26:52.135619+00:00；完整阅读后复核：2026-10-03T08:07:07.008373+00:00。

### ImageNet Classification with Deep Convolutional Neural Networks

- URL：https://proceedings.neurips.cc/paper_files/paper/2012/file/c399862d3b9d6b76c8436e924a68c45b-Paper.pdf
- PDF：`CV/alexnet2012.pdf`，SHA-256 `90137160c57217953d5f61857e64ca58e85f06e1b13b4f475c918b1b582b9771`。
- 提取：`CV/alexnet2012.pages.json`，SHA-256 `90ed6fb88132629932510857b8ae917021b9cc15b8fef3d96db640a62ff3d791`。
- 实际获取：2026-10-02T04:26:49.547633+00:00；完整阅读后复核：2026-10-03T08:07:07.008373+00:00。

### Deep Residual Learning for Image Recognition

- URL：https://openaccess.thecvf.com/content_cvpr_2016/papers/He_Deep_Residual_Learning_CVPR_2016_paper.pdf
- PDF：`CV/resnet2016.pdf`，SHA-256 `51b5de45eb0b558b19c3affe49503cff50cb170a32de602983d6e2ec286942a7`。
- 提取：`CV/resnet2016.pages.json`，SHA-256 `eb87d8cf83cb811d004b928193289870c6fd944ffba74dce11eb430770159736`。
- 实际获取：2026-10-02T04:26:47.313424+00:00；完整阅读后复核：2026-10-03T08:07:07.008373+00:00。

### Faster R-CNN: Towards Real-Time Object Detection with Region Proposal Networks

- URL：https://proceedings.neurips.cc/paper_files/paper/2015/file/14bfa6bb14875e45bba028a21ed38046-Paper.pdf
- PDF：`CV/fasterrcnn2015.pdf`，SHA-256 `fad7c52aae4a7197c2b85869440d691d3c666d02c6853b65544a293fb6e5395b`。
- 提取：`CV/fasterrcnn2015.pages.json`，SHA-256 `d6e1b46fdf39e413e2f1046e9344ae574aca43074956f65b10d17779715a76b5`。
- 实际获取：2026-10-02T04:26:49.378386+00:00；完整阅读后复核：2026-10-03T08:07:07.008373+00:00。

### U-Net: Convolutional Networks for Biomedical Image Segmentation

- URL：https://link.springer.com/content/pdf/10.1007/978-3-319-24574-4_28.pdf
- PDF：`CV/unet2015.pdf`，SHA-256 `12a66db7590fbdd0ee0877f69adaea8568ecb76287d2e47cfd685f3f6022509a`。
- 提取：`CV/unet2015.pages.json`，SHA-256 `5c7ba6a6f585a270f34992dc75dc9a8effb5cba7ddc7b0bc90d3649626929a32`。
- 实际获取：2026-10-02T04:27:08.282172+00:00；完整阅读后复核：2026-10-03T08:07:07.008373+00:00。

所有提取采用实际方法 `PyMuPDF 1.26.6 page.get_text("text", sort=False), PDF content order; exact Unicode strings, UTF-8 JSON without normalization. Figures/tables/equations separately visually inspected.`，保留 PyMuPDF 返回的原始 Unicode、连字及换行；未重排/归一化原文。每个证据 `context` 的 start/end 是该页 Python Unicode 字符串索引，SHA-256 来自实际切片 UTF-8 字节。

## 补充材料与版面核验

- resnet2016-supplemental：https://openaccess.thecvf.com/content_cvpr_2016/supplemental/He_Deep_Residual_Learning_2016_CVPR_supplemental.pdf；获取 2026-10-02T04:26:52.551148+00:00；原始包 SHA-256 `ab9b8a61194fc6a9cd1f8c57a5c3dbc7a832cbe33492f6f02cee97b3e4633bbf`。
- alexnet2012-supplemental：https://proceedings.neurips.cc/paper_files/paper/2012/file/c399862d3b9d6b76c8436e924a68c45b-Supplemental.zip；获取 2026-10-02T04:26:58.459275+00:00；原始包 SHA-256 `82ed715be2f9f2cbd8bde94f2760264d5c4f063e128334825e18a70a88802f7f`。
- fasterrcnn2015-supplemental：https://proceedings.neurips.cc/paper_files/paper/2015/file/14bfa6bb14875e45bba028a21ed38046-Supplemental.zip；获取 2026-10-02T04:26:58.378304+00:00；原始包 SHA-256 `a68eae3caefcdb37c829120c9df993d993844206b81b3aec75bcd2ed8881a9bf`。
- Faster ZIP 中实际 `rpn_supp.pdf`（2 页）SHA-256 `a07d5ec086c3d37397a9d8544bfd8ae1b75c7ef430f733b8ae2f958a9ca14b9f`；其提取 SHA-256 `c25d57ee421a2b6b7eecf809869a3eaadfbb778298d26cf34619ade2df2ca4eb`。
- U-Net 正式 8 页章节没有附加文本 appendix。作者项目页的补充入口另提供软件/训练模型包和结果展示视频；软件包不是额外论文页。正文主张均由正式 PDF 支撑。
- 可选 U-Net 视频：https://lmb.informatik.uni-freiburg.de/people/ronneber/u-net/u-net-teaser.mp4；实际获取 2026-10-02T04:39:40.130727+00:00；SHA-256 `4191028c8203f0c9d7cd44091cc2d003682c48cb9a7f7073e8e213d3e55b3376`，时长 303.929410 秒。已检查每 3 秒采样的 101 个帧及作者项目页；这是采样视觉检查，**不是逐帧完整观看或新增主张的证据**。导读没有采用视频独有结果。

已实际打开并检查以下渲染页；各页原图及拼版留在外部 `CV/renders/`。

|论文|版面检查（PDF 文件页）|解决的布局问题|
|---|---|---|
|SIFT|10、12、15、16、20、23|定位插值/曲率公式；Figure 7 示意 2×2 与实际 4×4×8=128 的区别；距离比与实例几何验证|
|HOG|2、4、5、6、8|Figure 1 扫描/NMS 顺序；Figures 3–5 误报-漏检曲线及归一化；Figure 6 头肩和脚部权重|
|AlexNet|3、5、6、7、8；全部补充定性图|ReLU 曲线；双 GPU 连接；滤波器；Tables 1–2 数据/单模型/集成/预训练区分；Figure 4 检索|
|ResNet|1、2、3、5、6、7、8；附录 1–4|相加后激活与式(1–2)；基本块/瓶颈；训练验证曲线；Tables 1–8；附录基线与比赛改进分开|
|Faster R-CNN|3、6、7、8；补充 1–2|RPN 双分支/锚框及式(1)；消融；Table 4 计时；召回曲线；补充逐类结果与定性框|
|U-Net|2、3、4、5、6、7|裁剪拼接和分块上下文；像素/细胞间隙权重；Table 1 指标列与排序；Table 2 交并比|

## 证据与字符预算

|论文|概述 Han / visible|六节合计 Han / visible|证据条目|
|---|---|---|---|
|`classic:cv:sift`|174 / 188|597 / 640|34|
|`classic:cv:hog`|179 / 193|606 / 654|26|
|`classic:cv:alexnet`|171 / 187|608 / 654|34|
|`classic:cv:resnet`|173 / 186|620 / 677|27|
|`classic:cv:faster-rcnn`|173 / 184|633 / 680|28|
|`classic:cv:unet`|168 / 179|623 / 674|33|

共 182 条中文逐字主张；覆盖 overview 和六节，技术细节、数量及唯一写出的残差公式分别有具体页/节/图表定位。工程用途、泛化边界和阅读建议以“据此/工程上/推断”标明 readerInference；context 保留支持推断的原文而不冒充论文已验证结论。

## 易混淆结果与约束

- SIFT 采用作者已接收稿的 28 页定位；尺度/旋转不变与视角鲁棒性分开。分区与插值允许位置偏移，归一化主要减弱照明影响；实例识别不转述成任意类别识别。
- HOG 默认九个无符号方向箱来自 p.4 §6。p.2 Figure 1 明确先在位置/尺度上扫描，再对输出执行 NMS；当前实验范围为大多可见直立行人。历史 MIT 比较的数据划分/负样本不足在 p.3 明示。
- AlexNet 官方网页摘要与链接的正式 PDF 不同：网页写 1.3M/39.7%/18.9%/两全连接，实际正式 PDF 写 1.2M/37.5%/17.0%/五卷积加三全连接。正文与证据只使用 PDF；p.7 Table 2 最优成绩来自含额外预训练的集成，未归给基本单模型。
- ResNet 使用 CVPR 正式版，式(1)后还接非线性；极深 CIFAR 模型低训练误差不等于更好测试误差。p.8 Tables 7–8 是受控检测基线；附录追加技巧、不同数据和集成的结果没有转移到该基线。
- Faster R-CNN 使用 NIPS 2015 原版四步交替优化，未引入后续扩展版联合训练结果。Table 4 只有候选附加层计时与整系统计时不同，SS 候选在 CPU，其余在 K40 GPU；候选召回仅为诊断而非最终 mAP。
- U-Net 为 Springer 正式页码 234–241；采用无填充卷积，需要裁剪/分块上下文。p.6 Table 1 按 warping error 排序，Rand/Pixel 列另有更低值；没有写成所有指标领先或无条件临床泛化。

## 字段门禁与冻结

本次在实际源文件仍存在时调用：

```python
validate_guides({'CV': data}, flat_catalog_records,
                as_of=date(2026, 10, 3),
                source_root=Path('/workspace/scratch/7877d1c29d91/guide-source-intermediates'))
```

结果：`ok=true`，`complete=false`（本次调用仅传 CV），`readyCount=6`，`candidateCount=0`，`CV=6`，`fullTextBytesRechecked=6`，`errors=[]`。原始报告保存在仓库外 `CV/field-validation.json`。目录仍按独立的 2026-10-01 锚点核验；导读新复核时间按当前 2026-10-03。

冻结的 `research/classic-guides/CV.json` SHA-256：`4d8b26e3ae0bbd0420742f9e4a9ebc084e78b46da333611cfce6e5e32528abba`。审计自身 hash 由交接消息另报，避免自包含散列。此冻结只表示字段自查完成，不替代整个集合的独立内容验收。
