# 来源核对与证据使用说明

核对日期：2026-09-16。正文文献编号与下表一致。检索用于核对与本稿论证直接相关的论文及官方资料，不称为系统性文献综述，也不据此宣称“首个”基准。

## 外部资料

| 编号 | 一手来源 | 已核对内容 | 使用边界 |
|---|---|---|---|
| 1 | [Evaluating Fuzz Testing，作者预印本](https://arxiv.org/abs/1808.09700) | 标题、作者、2018 年，以及评测设置影响结论的研究主题；ACM DOI 为 10.1145/3243734.3243804 | DOI 页面直接访问受限；不编造从该论文得到的本项目性能结论 |
| 2 | [AddressSanitizer，USENIX](https://www.usenix.org/conference/atc12/technical-sessions/presentation/serebryany) | 作者、会议信息、309–318 页、检测器研究对象 | 未引用其性能数字作为本项目性能 |
| 3 | [Juliet，NIST](https://www.nist.gov/publications/juliet-11-cc-and-java-test-suite) | 合成样例、作者、期刊年卷期、DOI | 不把合成直接等同于没有研究价值 |
| 4 | [CGC，DARPA](https://www.darpa.mil/research/programs/cyber-grand-challenge) | 专门构造的软件及任务环境 | 不宣称覆盖真实 C/C++ 软件的统计代表性已被量化 |
| 5 | [Magma，ACM](https://doi.org/10.1145/3428334)；[作者公开稿](https://adrian-herrera.com/assets/publications/magma.pdf) | 标题、作者、4(3)、Article 49、29 页、真实缺陷与漏洞中心评价 | 不使用本仓库未经本稿审计的“45/138”等数字批评 Magma |
| 6 | [UniFuzz，USENIX](https://www.usenix.org/conference/usenixsecurity21/presentation/li-yuwei)；[正式论文](https://www.usenix.org/system/files/sec21-li-yuwei.pdf) | 作者、2021、2777–2794 页；第 5–6 页附近的去重与 Ground Truth 讨论 | 原文确有漏洞分析与资料补充，不能说其没有漏洞信息 |
| 7 | [OSS-Fuzz 复现文档](https://google.github.io/oss-fuzz/advanced-topics/reproducing/) | 问题输入、harness、sanitizer 配置 | 持续测试服务不直接等同于本文固定版本的共同已知集合 |
| 8 | [ARVO 官方仓库](https://github.com/n132/ARVO) | 当前作者 BibTeX：EuroS&P 2026、860–873、DOI；可重建和触发的材料定位 | 6138 等本稿数字来自本地冻结输入，不能写成最新完整 ARVO 总量 |
| 9 | [FuzzBench 官方 FAQ](https://google.github.io/fuzzbench/faq/) | 引用信息、2021、1393–1403、DOI、评测服务定位 | 不把 FAQ 历史说法当成其所有当前功能的完整清单 |
| 10 | [BugOss 出版页](https://www.sciencedirect.com/science/article/pii/S016412122400164X)；[ASE 2024 作者论文介绍](https://conf.researchr.org/details/ase-2024/ase-2024-journal-first-papers/2/BUGOSS-A-Benchmark-of-Real-world-Regression-Bugs-for-Empirical-Investigation-of-Regr) | 两位作者、216 卷、112119、DOI、引入版本和共存故障问题 | 不声称本文首次注意到共存故障 |
| 11 | [Clang ASan 文档](https://clang.llvm.org/docs/AddressSanitizer.html) | 检测范围、相关构建选项、通常首错退出 | 不把单次无报告解释为绝对不存在缺陷 |
| 12 | [LLVM libFuzzer 文档](https://llvm.org/docs/LibFuzzer.html) | 覆盖反馈、入口契约、全局状态、通常建议保持入口聚焦 | 主动讨论聚合的搜索和状态代价，不预设聚合提速 |
| 13 | [Magma 缺陷目录](https://hexhive.epfl.ch/magma/docs/bugs.html)；[技术说明](https://hexhive.epfl.ch/magma/docs/technical.html) | 公开 ID/报告及不同观测事件 | 不否定 reached/triggered/detected 的定义区别 |
| 14 | [CWE官方目录](https://cwe.mitre.org/data/index.html)及正文所列五项定义 | 4.20版术语，越界读写、UAF、重复释放和未初始化变量使用 | 粗分类是本文调查归并口径，未强行赋予细粒度CWE或用标签代替身份 |

出版商网页存在部分 403、抓取限制或跳转失败时，使用作者稿、官方仓库或会议官方介绍补充；没有将第三方期刊聚合网站作为技术论断依据。所读资料支持本稿相应论断，不代表所有文献均已逐页精读。最终排版时可按期刊要求调整作者缩写及引用格式。

## 本地证据

`evidence/source_manifest.json` 给出 45 份统计来源的路径、大小和哈希。它们包括 6,138 条候选记录、64 项目录索引、37 份人工测量记录，以及分类和候选选择规则。哈希由现有本地文件计算，不涉及远程材料或目标二进制重新验证。

v4的表1为从评测任务推导的设计要求，表2为按同一要求组织的文献比较。表3仍与 `evidence/selected_projects.md` 一致，表4来自 aggregation 的输入检查记录，表5来自字段审计，表6连接设计要求、构建方法和已有证据。过程规模移到补充表S2，未改变原数字。图1与图2分别表达四项标准与campaign配置，以及标准—方法—核验流程，图3、图4仍使用原有组数/路由及字段矩阵。

前轮额外阅读 `memvul/catalog.py` 与 `memvul/gitutil.py`，哈希单列于 `evidence/method_source_manifest.json`，不改写原45份来源清单。原始观测原样导出到 `observation_register.json`，每行含来源 JSON Pointer，不重新归并报告或赋予计分身份。配置实例也是原字段摘录，不是已复建工件。

正文案例摘录原人工记录中的解释，未在本次写作中重新分析原始 ASan 日志或复核上游补丁。源码路径、PoC ID、指纹等仍由原记录支持；是否达到独立根因证明由后续人工审核决定。特别是 known_real 与 pending 字段的并存，不会被写作统计程序自动解决。

## 需要防止的统计误读

`source_commit` 是记录字段，不等于本次已经检验构建源码。`image_archive_sha256` 是已保存校验值，不等于本次重新散列大体积镜像。`verified_expected_matched` 是记录的匹配输入数，不等于独立漏洞数。`unique_expected_count` 是既有去重结果，不是本次重新执行根因去重。`benchmark_seat=in_set` 不是 `catalog_admission=admitted`。

## 2026-09-17 论证重构时的来源复核

再次核对[Magma官方说明](https://hexhive.epfl.ch/magma/)、[ARVO官方仓库](https://github.com/n132/ARVO)、[UniFuzz会议页面](https://www.usenix.org/conference/usenixsecurity21/presentation/li-yuwei)和[OSS-Fuzz复现文档](https://google.github.io/oss-fuzz/advanced-topics/reproducing/)。这些来源用于限制缺口论断。Magma已提供真实程序、历史漏洞与条件观测；ARVO强调逐漏洞可重建、触发和分析；UniFuzz提供真实程序与多指标评测；OSS-Fuzz提供问题复现信息。因此v3不把这些已有能力写成不存在，联合要求下仍需专门构建的结论是本文按C1–C5作出的范围限定分析，不是穷尽检索证明不存在任何合适基准。

20项目的建设目标来自作者2026-09-17的明确说明，而不是由64/37的处理数量反推。不称这一目标已预注册，也不据其推导最佳样本量或总体代表性。


## v4 标准对齐与证据边界（2026-09-17）

四项设计标准及真实性优先顺序来自作者讨论与本文的任务分析，属于规范性设计主张；已有文献用于说明任务背景、资源特征及测量风险，不冒充标准已获普遍认可的证据。数量对有效评估粒度与整体效能的意义仅作定性论证。正文中的C=(F,S,U,T)和已知集合下界取代v3旧元组。

类型术语依据CWE官方定义，粗分类及其边界见正文第2.3节与补充材料 S1.10；保留原标签、多表现和未知。CWE不是按sanitizer报告自动分配根因身份的工具。

仓库另有 `third_party/magma-v1.2.1-official-replay.md` 的先行比较笔记，属于待核验线索。其统计范围、类型规则、观测事件及运行明细需与本文口径对齐后再引用。本稿未将笔记数字升级为跨benchmark实测结论；尤其不从有限PoC未触发推断某harness无法触发，也不将canary与ASan检测混作同一事件。

本轮缺口审查属于作者主导修订，未新增独立审稿或正式编辑决定。新gap文档区分文字已改与工件待验；表6各项均保留实证边界。
