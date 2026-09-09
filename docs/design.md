# MemVulBench 设计

面向 C/C++ **内存安全**漏洞挖掘研究的高密度、崩溃可验证 benchmark。

## 1. 为什么现有测试集不够用

三个候选各缺一角，且缺的不是同一角：

| 测试集 | 密度 | 真值单元 | 关键缺陷 |
|---|---|---|---|
| Magma | 高（138 canary / 9 项目） | 手写谓词 `MAGMA_LOG(id, cond)` | 谓词是**未经验证的代理**；本机实测 138 条中 `canary_only` 89、`native_crash` 35、`asan_only` 10、`timeout` 4 —— 只有 **45/138 (32.6%)** 在真实测试场景下可观测 |
| OSS-Fuzz / ARVO | 极低（1 bug / 镜像） | ASan/MSan 报告（sound） | 一次战役只产出 1 个二元结果，统计功效不足以支撑对比实验 |
| UniFuzz | 未知 | 无公开清单 | SAND 报告的 204 个 bug 无 PoC、无 ID，各家不可比 |

Magma 的**结构**是对的（多漏洞共驻一个程序 + 稳定 ID + 探针），ARVO 的**真值**是对的（sanitizer 报告即证据，PoC 齐全）。
MemVulBench = **Magma 的密度 × ARVO 的严谨**。

### 1.1 Magma 失效的根因

`MAGMA_LOG(id, cond)` 里的 `cond` 是人工从 CVE 描述反推的谓词。它回答的是
"某个可疑条件成立了吗"，而不是"内存安全真的被违反了吗"。二者在前向移植
（把老漏洞塞进新版本代码）之后大面积脱钩：周边代码已经变了，谓词还能成立，
但越界写落进了同一个 malloc chunk 的 usable size 里，或者根本没有实际的
非法访问发生。实测的 89 个 `canary_only` 中，68 个是"canary 触发而 ASan 完全沉默"。

**结论：真值不能是人写的谓词，必须是可复现的崩溃见证（crash witness）。**

## 2. 核心设计决策

### D1：真值 = 崩溃见证，不是谓词

每个漏洞的 ground truth 是一条**已验证的 oracle 报告**，而不是源码里的 `if`。
入库时对每个 PoC 跑一遍 **oracle 矩阵**，记录哪些 oracle 开火、报告指纹是什么：

| oracle | 构建 | 记录 |
|---|---|---|
| `native` | `-O2`，无 sanitizer | 信号 / 退出码 |
| `asan` | `-fsanitize=address` | 报告类型 + 崩溃帧 + 分配帧 |
| `asan-recover` | `+ -fsanitize-recover=address` | 同上，且可继续执行 |
| `msan` | `-fsanitize=memory` | 未初始化读 |
| `ubsan` | `-fsanitize=undefined` | UB 类型 |
| `valgrind` | native 二进制 | memcheck 报告 |

ARVO 的漏洞按构造就已经是 sanitizer 验证过的，所以这一层基本自动通过 ——
这正是相对 Magma 的结构性优势。

### D2：只收实际可观测的漏洞

准入的硬门槛是**可发现性**：漏洞必须在 native 或 ASan 下确定性地开火。
理由是研究口径的一致性 —— 一个现成工具在真实测试场景下根本看不见的漏洞，
放进测试集只会稀释指标、制造不可比的数字，这正是 Magma 138 条里
89 条 `canary_only` 造成的问题。

被排除的两类，各自的排除理由不同，都要记账（见 [schema.md](schema.md) §3）：

- `all_oracles_silent`：无任何 oracle 见证 —— 根本没有证据表明发生了内存违规。
- ASan 沉默但更强 oracle（Valgrind / MSan / 子对象检查器）有见证：
  确属内存违规，但不在本测试集的可发现性口径内。
  **单独记入 `data/excluded/`，不进主目录。** 这批样本对检测器（sanitizer）
  研究有价值，留作后续扩展的素材，但不参与任何主赛道指标。

其余分类信息（空间/时效、CWE、oracle 矩阵）全部保留并随漏洞发布，
让使用者可以按需要做子集切分。

### D3：密度化 = 文件级时间 pin

ARVO 每个镜像 1 个 bug。要拿到 Magma 级密度，需要把同一 (project, harness)
下的 N 个历史漏洞塞进同一个 build。

**原设计的"机械回退修复补丁"已被实测否定**：assimp 上 12/12 补丁干净应用，
但只有 3/14 真正复现（21%），而同一基线上天然潜伏的漏洞是 6/6。
补丁能否应用完全不能预测漏洞能否重现——因为漏洞不是补丁的逆运算，
而是某个文件在某一时刻的整体形态。

改用唯一原语 `pin(F, C)`：把文件 F 固定到上游 commit C 的 blob。
切片 = 基线 `B` + pin 表。由此得到一条可机械复验的**保真不变式**：

> 切片中每个参与编译的源文件都逐字节等于某个上游 commit 的 blob。

"考古"（pin 表为空）与"合成"（pin 认领文件到窗口内 commit）统一为同一操作，
回退则被彻底废弃——它是唯一会生成非上游文件的操作。

完整方法论见 **[methodology.md](methodology.md)**：认领集与扩张阶梯、
开关即换 pin、冲突图与切片构造、拼装预算、存活窗口的实测。

### D4：准入闸门（每个漏洞必须全过）

一个漏洞 i 进入 slice S（基线 B + pin 表）当且仅当：

1. **构建通过**：`B + pins(S)` 能编译出所有 oracle 变体。
2. **保真**：每个源文件逐字节等于记录的上游 blob（tier-2 则每个 pin 函数逐字节等价）。
3. **PoC 复现**：`poc_i` 在 oracle build 上产出的报告指纹匹配 ARVO 参考指纹
   （crash_type + 崩溃函数 + 源文件；行号允许漂移）。
4. **负对照**：把漏洞 i 切到 OFF（认领文件换成 fix-pin）、其余不变，`poc_i` **不崩溃**。
   → 证明崩的确实是这个漏洞。Magma 缺的就是这一条。
5. **隔离对照**：`poc_i` 在只开漏洞 i 的构建上同样复现；与条件 3 的差异记为**干扰量**。
6. **崩溃点可区分**：指纹与 slice 内其他漏洞不冲突（否则合并为同一 bug ID）。

条件 4、5 由开关机制免费提供（同一棵源码树，configure 阶段选装文件），
不需要单独维护干净树。

**确定性闸门本轮暂缓**（设计见 [determinism.md](determinism.md)），
待搬运方法论跑通后再接入。

任何一条不过 → 该漏洞出局，并记录失败原因（产出物之一：**移植失败率分析**）。

### D5：双构建，测量不污染被测工具

Magma 把探针编进被测二进制，同时改变了覆盖率反馈和吞吐。MemVulBench 分离：

- **eval build**：被测工具实际跑的二进制。**不含任何 MemVulBench 探针**，
  sanitizer 配置由实验设定。零测量偏差。
- **oracle build**：同源同 commit，`asan-recover` + 全漏洞点探针 +
  `halt_on_error=0`，确定性配置。**只在战役结束后离线重放用**。

战役结束后，把工具保存过的**全部输入**（queue + crashes，带时间戳）灌进
oracle build，导出每个漏洞的 reached / triggered 时刻。

### D6：R → T → D 漏斗

| 层 | 定义 | 如何测 |
|---|---|---|
| **Reached** | 漏洞点代码被执行 | 探针，位置**自动**从 fix patch 的 hunk 推导 |
| **Triggered** | 内存违规真的发生了 | oracle build 的 ASan-recover 报告匹配指纹。**无需人写谓词** |
| **Detected** | 被测工具自己的 oracle 报出来了 | 工具 `crashes/` 里的输入归因到 bug ID |

恒有 `R ⊇ T ⊇ D`。Magma 只有 R 和（不可靠的）T。

两个 gap 本身就是可发表的观测量：

- `R \ T`：路径到了但没打穿 —— 输入生成精度的度量。
- `T \ D`：真的越界了但工具没报 —— **检测机制（sanitizer）强弱的度量**。
  这正是 BoostFuzz / rangesanitizer 需要的靶场。

## 3. 产出物结构

```
MemVulBench/
├── docs/            design.md（本文）/ methodology.md / schema.md / determinism.md / adr/
├── memvul/          Python 包：sweep / base / pin / slice / verify / emit / attribute
├── catalog/         漏洞真值（进 git，纯文本）
│   └── <project>/<harness>/<BUGID>/
│       ├── bug.yaml           元数据 + 窗口 + pin 对 + oracle 矩阵 + 指纹
│       ├── probe.patch        自动生成的 reached 探针
│       ├── poc/               触发输入
│       └── oracle/            各 oracle 的参考报告
├── targets/<project>/
│   ├── memvul.yaml   基线 commit、harness、slice 定义
│   ├── pins.yaml     切片的完整 pin 表（文件 → 上游 commit），保真复验的依据
│   ├── Dockerfile
│   └── build.sh
└── data/            普查与实验结果（大文件不进 git）
```

漏洞 ID：`<PROJ3>-<NNN>`，如 `HFB-001`（harfbuzz）。稳定不复用，
并保留到 OSS-Fuzz issue id / ARVO id / CVE 的映射。

## 4. 评测协议要点

- **主指标**：预算内发现的不同漏洞数；每漏洞首次发现时间 TTD。
- **统计**：≥10 次重复、24h；Kaplan-Meier 生存曲线 + 每漏洞 TTD 的
  Mann-Whitney U（遵循 Klees et al. 的口径）。
- **诊断指标**：`R\T`、`T\D` 两个 gap；崩溃归因的 precision/recall；
  去重负担（唯一崩溃簇数 / 真实漏洞数）。
- **落盘约束**：NTFS 分区只放代码和元数据；构建与战役工作目录必须在 ext4。

## 5. 已知风险

| 风险 | 缓解 |
|---|---|
| 拼装树是历史上不存在的程序 | 量化并公布 `mosaic_ratio` / `temporal_spread`；提供零 pin 的 `pure` 档 |
| pin 后漏洞不可达（Magma 病） | D4 条件 3/4 强制拦截；认领集按 [methodology.md](methodology.md) §3 阶梯扩张 |
| 认领集扩张导致冲突、slice 太碎 | 接受多 slice；把冲突率与扩张层级本身作为结果报告 |
| 单体架构项目冲突率高、密度上限低 | 把模块化程度写进选片打分（methodology.md §5），不强行拉高密度 |
| 多漏洞互相掩蔽（先崩的挡住后面的） | oracle build 用 `-fsanitize-recover` + `halt_on_error=0`；掩蔽率由 D4 条件 5 直接测出 |
| 崩溃点重合导致归因歧义 | D4 条件 6：指纹冲突则合并为同一 bug |
| 仅重放"保存过的输入"会低估 R/T | 明确口径：主指标 D 完整无偏；R/T 标为诊断量。另提供 Magma 兼容的在线探针模式 |
