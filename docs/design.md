# MemVulBench 设计

面向 C/C++ **内存安全**漏洞挖掘研究的高密度、崩溃可验证评测平台。

## 0. 定位

**这不是一个要独立发表的 benchmark artifact，而是支撑 fuzzing 技术研究的评测平台。**
唯一的成功判据是能不能可信地支撑"本方法比 baseline 发现更多漏洞"这个主张。

因此凡是为了"benchmark 本身作为科学工件站得住"而付出的成本——难度标定、密度失真量化、
未知漏洞普查、确定性契约——一律不做，放弃的理由与代价记在
[methodology.md](methodology.md) §10。构建路线是**纯考古**：目标即上游某个未经修改的
commit，漏洞即该 commit 上 PoC 实际开火的那批。

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

### D3：密度化 = 纯考古，不做任何源码改动

ARVO 每个镜像 1 个 bug，一次战役只产出 1 个二元结果，统计功效不足。
提高密度是为了解决这个问题——但**不是靠把漏洞搬到一起，而是靠找到它们本来就在一起的时刻**。

两条被实测淘汰的路线：

- **修复回退**：assimp 上 12/12 补丁干净应用，只有 3/14 真正复现（21%）。
  补丁能否应用完全不能预测漏洞能否重现，因为漏洞不是补丁的逆运算。**已废弃。**
- **文件级时间 pin**：未被否定，但为了把单目标密度从 8 推到 26，需要认领集扩张阶梯、
  冲突图、最大独立集、保真 manifest、存活窗口实测——工程量是十倍，收益是边际的。
  **降级为可选增量**（[methodology.md](methodology.md) §9），本轮搁置。

同一试点的第三行才是结论：**不做任何改动时，天然潜伏漏洞的复现率是 6/6（100%）。**

于是唯一的构建操作是选一个 commit：

```
target = 上游某个 commit C，未经任何修改
bugs   = 在 C 上构建后 PoC 实际开火、且指纹匹配的那批漏洞
```

单目标密度因此受历史支配（预期 6–12），总漏洞数改由**目标数量**提供：
12 个目标 × 8–10 个 ≈ 100+ 个已验证可观测漏洞，是 Magma 可观测数（45）的两倍以上。
本质是用算力换工程量——算力可以排队，写求解器的时间不能。

找基线的方法见 [methodology.md](methodology.md) §4：OSS-Fuzz 接入初期的**批量修复日**
就是天然密度的局部峰值，候选基线可纯靠元数据算出，零构建成本。

### D4：准入闸门（三条）

一个漏洞 i 进入目标（基线 C）当且仅当：

1. **开火**：`poc_i` 在基线二进制上产生 ASan 报告或信号。
2. **指纹匹配**：报告指纹匹配 ARVO 参考指纹（`kind` + `access` + 崩溃函数 + 源文件；
   行号允许漂移）。**这是防 Magma 病的唯一一道，也是必需的一道**——崩了不等于崩的是那个漏洞。
3. **可区分**：指纹在本目标内唯一；与其他漏洞相同则合并为一个 bug ID。

原设计的**负对照、隔离对照、保真闸门全部取消**：目标就是上游 commit 的原貌，
漏洞本来就在树上，不存在"崩溃是不是我的改动造成的"这个问题，保真也平凡满足。
这是纯考古路线相对 pin 路线最大的成本下降。

**确定性闸门不接入**（设计见 [determinism.md](determinism.md)）。
关 ASLR + 固定 `ASAN_OPTIONS` 对 TTD 统计已经足够。

任何一条不过 → 该漏洞出局并记录原因。

### D5：双构建，测量不污染被测工具

Magma 把探针编进被测二进制，同时改变了覆盖率反馈和吞吐。MemVulBench 分离：

- **eval build**：被测工具实际跑的二进制。**不含任何 MemVulBench 探针**，
  标准 ASan 配置。零测量偏差。
- **recover build**：同源同 commit，`-fsanitize-recover=address` + `halt_on_error=0`。
  **只在战役结束后离线重放用**，不参与战役。

recover build 的作用是**补捞被掩蔽的漏洞**：一个输入同时踩中 3 号和 7 号时，
正常 ASan 只报 3 号。战役结束后把工具存下的全部输入（queue + crashes，带时间戳）
灌一遍 recover build，就能还原完整的触发集合。这一步很便宜，但直接提高可报告的漏洞数。

### D6：T → D 两层

| 层 | 定义 | 如何测 |
|---|---|---|
| **Triggered** | 内存违规真的发生了 | recover build 的报告匹配指纹。**无需人写谓词** |
| **Detected** | 被测工具自己的 oracle 报出来了 | 工具 `crashes/` 里的输入归因到 bug ID |

恒有 `T ⊇ D`。`T \ D` 是真的越界了但工具没报，即**检测机制强弱的度量**。

**Reached 层（探针）本轮不做。** 它需要从 fix patch 的 hunk 自动推导探针位置并插桩，
是纯粹的工程成本，且只在研究方向明确关心"路径可达性"时才有价值。
需要时再按 Magma 的方式补，不影响其余设计。

## 3. 产出物结构

```
MemVulBench/
├── docs/            design.md（本文）/ methodology.md / schema.md / determinism.md / adr/
├── memvul/          Python 包：census / candidates / sweep / base / verify / emit
├── targets/<project>/
│   ├── target.yaml            基线 commit、harness、漏洞清单
│   ├── Dockerfile             基于 ARVO 镜像，checkout 到基线
│   ├── replay.sh              回放与归因
│   └── bugs/<BUGID>/
│       ├── bug.yaml           元数据 + oracle 矩阵 + 指纹
│       ├── poc/               触发输入
│       └── oracle/            参考 ASan 报告
└── data/            普查、候选基线、sweep 结果（大文件不进 git）
```

目标的完整定义就是 `target.yaml` 里的一个 commit sha —— 任何人 `git checkout` 即可复验，
不需要 pin 表、manifest 或保真论证。

漏洞 ID：`<PROJ3>-<NNN>`，如 `HFB-001`（harfbuzz）。稳定不复用，
并保留到 OSS-Fuzz issue id / ARVO id / CVE 的映射。

## 4. 评测协议要点

- **主指标**：预算内发现的不同漏洞数；每漏洞首次发现时间 TTD。
- **统计**：≥10 次重复、24h；Kaplan-Meier 生存曲线 + 每漏洞 TTD 的
  Mann-Whitney U 与 Vargha-Delaney Â₁₂（遵循 Klees et al. 的口径）。
- **种子集统一，且绝不含任何 PoC 或其变体。** 种子选择是已知的头号混淆因素。
- **归因**：工具 `crashes/` 里的输入灌进 recover build，按指纹映射到 bug ID；
  归不到任何已知漏洞的崩溃簇单独报出，不计入主指标。
- **对外主张必须同时附 Magma 或 FuzzBench 的结果**：自建集是补充证据，不是唯一证据。
- **落盘约束**：NTFS 分区只放代码和元数据；构建与战役工作目录必须在 ext4。

## 5. 已知风险

| 风险 | 缓解 |
|---|---|
| 天然密度不够，单目标只有 3–5 个漏洞 | 先跑数据再判断；不够时按 [methodology.md](methodology.md) §9 补机会主义 pin |
| 崩了但崩的不是那个漏洞（Magma 病） | D4 条件 2 指纹匹配强制拦截 |
| 多漏洞互相掩蔽（先崩的挡住后面的） | 战役后用 recover build 离线补捞（D5） |
| 崩溃点重合导致归因歧义 | D4 条件 3：指纹冲突则合并为同一 bug |
| 基线上存在未编目的未知漏洞，败坏归因分母 | 未归因崩溃簇单独报出；sweep 产量并列时取时间较晚的基线 |
| 漏洞难度未标定，等权计数可能分辨率不足 | 报每漏洞 TTD 曲线而非只报总数，分布交给读者判断 |
| 语料全部来自 OSS-Fuzz 已发现的漏洞，难度天花板被封死 | **无解**，写进论文局限性（测的是速度，不是能力边界） |
