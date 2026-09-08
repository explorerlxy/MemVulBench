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

### D2：三档可观测性分层

用户的核心诉求是"不可发现的漏洞对测试没有意义"。但直接用"ASan 必须开火"
做准入门槛会误删一类高价值样本：**真实的内存违规但 ASan 看不见**
（子对象/结构体内越界、intra-object overflow）——这恰恰是 rangesanitizer /
SoftBoundCETS 这类检测器研究的靶心。所以不做删除，做**分层标注**：

- **Tier-A（主赛道，评测 fuzzer）**：native 崩溃 或 ASan 开火。可被现成工具发现。
- **Tier-B（检测器赛道）**：确属内存违规，但仅被更强 oracle（Valgrind /
  子对象检查器 / MSan）捕获，ASan 沉默。**这是没有任何现有 benchmark 提供的集合。**
- **Tier-C（拒收）**：无任何 oracle 能给出内存违规见证 —— 即 Magma 的 `canary_only`。

Tier-A 满足"可发现性"，Tier-B 是差异化贡献且直接服务本人的 sanitizer 研究。

### D3：密度化 = 修复回退（fix-reversal），逐个验证

ARVO 每个镜像 1 个 bug。要拿到 Magma 级密度，需要把同一 (project, harness)
下的 N 个历史漏洞塞进同一个 build。

不采用 Magma 的手工前向移植（正是它 silent bug 的来源），改用**机械回退修复补丁**：

```
选定基线 commit B
  for each bug i:  apply  revert(fix_commit_i)  onto B
  求最大兼容集（互不冲突的 revert 子集）→ 一个 slice
```

回退补丁比前向移植可靠得多：安全修复通常是小而局部的改动，且 `git revert`
的成败是机械可判定的。真正的保证来自**逐个验证**（见 D4），不来自人工判断。

冲突不可避免。做法是把一个 (project, harness) 切成若干 **slice**，每个 slice
内部的 revert 互相兼容；slice 是评测的基本单位。

### D4：准入闸门（每个漏洞必须全过）

一个漏洞 i 进入 slice S（基线 B）当且仅当：

1. **构建通过**：`B + reverts(S)` 能编译出所有 oracle 变体。
2. **PoC 复现**：`poc_i` 在 oracle build 上产出的报告指纹匹配 ARVO 参考指纹
   （crash_type + 崩溃函数 + 源文件；行号允许漂移）。
3. **对照阴性**：`poc_i` 在**未回退**的干净基线 B 上**不崩溃**。
   → 证明是 revert 重新引入了漏洞，而不是碰巧触发了别的东西。
   Magma 缺的就是这一条。
4. **确定性**：5 次重放 5 次一致（ASLR 关闭、单线程、固定 allocator 选项）。
5. **共驻不失效**：在完整 slice 二进制上 `poc_i` 仍然复现 bug i。
6. **崩溃点可区分**：指纹与 slice 内其他漏洞不冲突（否则合并为同一 bug ID）。

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
├── docs/            design.md（本文）/ schema.md / protocol.md / adr/
├── memvul/          Python 包：ingest / select / build / verify / attribute / report
├── catalog/         漏洞真值（进 git，纯文本）
│   └── <project>/<harness>/<BUGID>/
│       ├── bug.yaml           元数据 + oracle 矩阵 + 指纹
│       ├── reintroduce.patch  revert(fix_commit) 的落地版本
│       ├── probe.patch        自动生成的 reached 探针
│       ├── poc/               触发输入
│       └── oracle/            各 oracle 的参考报告
├── targets/<project>/
│   ├── memvul.yaml   基线 commit、harness、slice 定义
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
| revert 冲突率高，slice 太碎 | 按 (project, harness) 分片；接受多 slice；把失败率本身作为结果报告 |
| 回退后漏洞不可达（Magma 病） | D4 条件 2/3 强制拦截 |
| 多漏洞互相掩蔽（先崩的挡住后面的） | oracle build 用 `-fsanitize-recover` + `halt_on_error=0` |
| 崩溃点重合导致归因歧义 | D4 条件 6：指纹冲突则合并为同一 bug |
| 仅重放"保存过的输入"会低估 R/T | 明确口径：主指标 D 完整无偏；R/T 标为诊断量。另提供 Magma 兼容的在线探针模式 |
