# `known_real` 口径与 2026-09-14 核验

> **状态：2026-09-14 的四元组核验备忘。**
>
> 现行计分身份是最终入口五元组（2026-09-18 准入）。额外组现为 5 个
> （ghostpdl 1、libavc 1、openh264 2、arrow 1——BitReader negative-size，
> 随 2026-09-18 arrow 替换 librawspeed 入集），已计入已核验 292。
> 下文数字是当时的 4 元组审查，不覆盖现行账本。

核验时间：2026-09-14 11:05（Asia/Shanghai）。
对象：19 份 `data/measure/manual/` 回放记录。
本文件是当时的指标定义；现行准入见 `data/measure/admission/2026-09-18.json`。

## 1. 新口径

`known_real` 统计的是 **漏洞**，不是 PoC 条数。

一条基线指纹计入 `known_real` 当且仅当同时成立：

1. 固定基线上可复现的 ASan / SEGV 内存安全故障。
2. 指纹 `(kind, access, crash_func, crash_file)` 不在该项目本轮 **expected** 集合里。
   expected = 本 PoC 的目录 ARVO 指纹精确匹配（或已按 D4 合并进同一 expected bug ID 的等价栈）。
3. 它不是下列任一情形的再计数：
   - 与某条 expected 指纹相同（后到的 PoC 先死在已计入的洞上）；
   - `same_as_catalogued`：只是本 PoC 目录位点的 sanitizer 类别 / 栈帧漂移；
   - 同一目录走路上的更早 ASan 中止（例如 malloc 在 memcpy-overlap 之前开火）。
4. 源码路径与修复提交能证明这是独立的真实缺陷。无法闭环的异常仍按 D4 出局（unmatched），不得记 `known_real`。

单位：去重后的指纹 = 1。多条 PoC 打到同一指纹只加 PoC 旁注，不加漏洞数。

旧口径作废：把「撞上已计入 expected 的洞」「同洞 sanitizer 漂移」「同走更早中止」按 PoC 计进 23。

## 2. 核验结果

旧合计：23 条独立 `verdict: known_real` + 若干折进 expected 的 † 旁注。
新合计：**3 个** unique `known_real` 漏洞（5 条支撑 PoC）。

| 项目 | 旧记账 | 新 unique | 处置 |
|---|---|---:|---|
| ghostpdl | 22 PoC / 5 指纹 | **1** | 21 条撞上已有 expected；42514830 保留 |
| arrow | 2 PoC †（曾算进 expected） | **1** | 移出 expected；BitReader negative-size 不是目录 DeltaByteArray |
| libavc | 2 PoC †（曾算进 expected） | **1** | 移出 expected；空函数指针 SEGV 未到达目录 heap-overflow |
| sleuthkit | 1 PoC | **0** | 目录 memcpy-overlap 同走，更早 `allocation-size-too-big` |
| upx | 7 † | **0** | 全部 `same_as_catalogued`，已在 expected |
| libraw | 1 † | **0** | 同上 |
| 其余 13 个 | 0 | 0 | 无候选 |

### 2.1 保留的 3 个 unique

**arrow-parquet-leveldecoder-negative-size**（PoC 42504313、42504668）

- 实测：`negative-size-param` / `BitReader::BitReader` / `bit_stream_utils.h`
- 目录：`DeltaByteArrayDecoder::GetInternal` 的 memcpy-overlap / heap-OOB
- `same_as_catalogued: false`。负 RLE level 在 LevelDecoder::SetData 进入 BitReader；目录那两个 DeltaByteArray 修复碰不到这条路径。
- 从 `expected_signature_count` 扣除 2 条 PoC。arrow expected：9 → 7。密度从 ≥8 降到 7。

**libavc-svc-null-dispatch**（PoC 42530559、42530568）

- 实测：`SEGV READ null` @ `isvcd_parse_inter_slice_data_cavlc_enh_lyr`
- 目录：两条不同的 heap-overflow（`isvcd_process_residual_resample_mb`、`ih264d_motion_compensate_bp`）
- `same_as_catalogued: false`。基线确定性走到 `isvcd_parse_epslice.c:1908` 空分派；未到达目录溢出点。e49a9150 硬化的是同一畸形 SVC 家族，但崩溃位点不同，按指纹不去重进 expected。
- libavc expected：12 → 10。

**ghostpdl-ifree-zeropage**（PoC 42514830）

- 实测：`SEGV` @ `i_free_object` / `gsalloc.c`，地址 `0x30`，经 `show_cache_setup` / `pdfi_Tj`
- 目录：`gs_device_pdfwrite_fuzzer` 上 `gp_fflush` heap-OOB（本树无该 harness）
- 该指纹不在 ghostpdl 34 条 expected 里，也不是 wave 成员 `search_table_1` / `pdfi_set_input_stream` / `pdfi_repair_file` / `pdfi_dict_get`。
- 目录 pdfwrite 修复 `c43a98a5` 不能当作本位点的修复闭环；保留为 unique，是因为零页 SEGV 是独立的可复现内存安全故障，且与 expected 集合不相交。后续若审出与某条 expected UAF 同源，应降为 `collides_with_expected`。

### 2.2 剔除

**ghostpdl 21 条 → `collides_with_expected`**

指纹已在 expected 里（另有匹配 PoC）：

| 指纹 | PoC 数 | 已有 expected 代表 |
|---|---:|---|
| `global-buffer-overflow` `search_table_1` `pdf_int.c` | 13 | 有 |
| `memcpy-param-overlap` `pdfi_set_input_stream` `ghostpdf.c` | 6 | 有 |
| `global-buffer-overflow` `pdfi_dict_get` `pdf_dict.c` | 1 | 有 |
| `heap-buffer-overflow` `pdfi_repair_file` `pdf_repair.c` | 1 | 有 |

这些 PoC 的目录位点是更晚的 device / 同 harness 点；基线上先死在 2021-12-14 仍未修的 wave 洞。崩了，但复现的不是目录里那个 ID，也不是新洞。

**sleuthkit 42534995 → `catalog_earlier_abort`**

目录指纹是 `memcpy-param-overlap` / `tsk_fs_load_file_action` / `fs_load.c`。
实测是 `allocation-size-too-big` / `tsk_malloc` / `ntfs_dir_open_meta`：`$IDX_ALLOC` 的 `nrd.allocsize=0xffffffffffffff00` 在下一步 memcpy 之前被 ASan 拦住。
同走、更早中止，不是 expected 之外的新洞。也不升为 expected（D4 仍要求指纹匹配）。

**upx 7、libraw 1**

`same_as_catalogued: true`，观察指纹只是目录位点的类别/栈漂移，已计入 expected。`known_real_unique_count = 0`。

## 3. 回放合计（口径切换后）

502 条 PoC 重新切分：

| 判定 | PoC | 说明 |
|---|---:|---|
| expected | 195 | 原 199，减去 arrow 2 + libavc 2 |
| known_real（unique 漏洞） | 5 PoC / **3** 洞 | arrow 2 + libavc 2 + ghostpdl 1 |
| collides_with_expected | 21 | 仅 ghostpdl |
| catalog_earlier_abort | 1 | sleuthkit 42534995 |
| clean | 228 | 不变 |
| leak-only | 45 | 不变 |
| unmatched | 6 | 不变 |
| OOM | 1 | mruby 401868632；见 §5 |

最终 benchmark 准入按 **去重 expected 指纹 + unique known_real ≥ 8**，不是
「回放了 ≥ 8 条 PoC」。当时 12 个项目达标（含 arrow：7 + 1 = 8）。pcre2（4）
与 6 个低密度项目（≤ 3）直接 pass。

2026-09-16 正式 20 席已重选：espeak-ng / ndpi 入集，arrow / lwan 归档
（见 [build-progress.md](build-progress.md)）。本节仍是 09-14 的 KR 口径核验，不改写。

未匹配的 6 条 PoC 不是 known_real：崩了，但对不上目录指纹，也没有独立漏洞闭环。
见 §4。

## 4. 未匹配的 6 条 PoC

`unmatched` = 进程异常退出，但既不是该 PoC 的目录指纹，也不能收成 unique
`known_real`。502 里有 6 条，分三组：

| 项目 | OSS-Fuzz ID | 实测 | 为何不算 expected / known_real |
|---|---|---|---|
| arrow | 42486519、42489398、42489691 | `unmatched_abort`，`type.cc:517` 拒绝无符号 dictionary index | 断言式 abort，没有 ASan 内存安全报告，也到不了目录位点 |
| c-blosc2 | 42491774 | `allocation-size-too-big` @ harness `malloc` / `fuzz_decompress_frame.c` | 卡在 fuzzer 自己的输出缓冲分配；`allocator_may_return_null=1` 时变 clean，目标函数未到达 |
| libredwg | 42519555、42524318 | 同一 `heap-buffer-overflow WRITE decode_preR13_section_hdr` | 真 ASan，但是 pre-R13 DWG 解码路径；目录写的是 `out_json.c` 的 json_header_write。出处对不上，未做修复闭环，故不改标 |

## 5. mruby OOM 401868632

运行时观察仍是 `verdict: oom`（libFuzzer RSS，退出码 71，`malloc(2147483648)`）。这不是新的 unique `known_real`，也还不能改写成 expected。

更深一层：

1. **目录位点存在于基线。**
   `6b3b1012`（2021-10-12）的 `src/range.c` 已有 `range_num_to_a`。整数区间在 `mrb_int_sub_overflow` 之后直接 `mrb_ary_new_capa(mrb, len)`，**没有** `len == MRB_INT_MAX` 守卫。
2. **修复在基线之后很久。**
   `f4de2059`（2025-03-10）给闭区间补了 `len == MRB_INT_MAX` 则 `RangeError`，并减少大整数走 float 的精度丢失。commit 说明写的就是接近 `MRB_INT_MAX` 的长度计算。
3. **目录 `not_latent` / `fix_landed` 是 wave_eve 标签误用。**
   `score_eve(..., horizon_days=730)` 把「修复未落地且两年内落地」以外的条目一律写成 `not_latent` + `fix_landed`。本条修复距 eve 约 1245 天，被 730 天窗口剔出潜伏上界；**并不是** `f4de2059` 已是 `6b3b1012` 的祖先。
4. **OOM 就是这条长度 bug 的第一现场。**
   基线先按错误 `len` 去 `mrb_ary_new_capa`，ASan 看到 `malloc(2GiB)`，libFuzzer RSS 限额先杀进程（exit 71）。OSS-Fuzz 后来在修复前的树上看到的是 `heap-buffer-overflow WRITE range_num_to_a`——同一原语的后一阶段。
5. **为什么不能记 expected / known_real。**
   没有 ASan/SEGV 指纹，对不上目录 `(heap-buffer-overflow, WRITE, range_num_to_a, range.c)`。OOM 也不是独立于该目录位点的新洞。
6. **若要闭环 expected，需要另一次人工回放**（不在本次自动执行）：提高/关闭 `rss_limit_mb`，或让分配失败走 ASan `allocation-size-too-big` / 后续 OOB，看是否出现目录指纹。对照条目 42485317 在 `allocator_may_return_null=1` 下把超大分配收成 clean，说明分配器选项会改变第一现场。

结论：401868632 保持 `oom`；分析记为 **目录 `range_num_to_a` 长度缺陷的分配器第一现场**，不是独立漏洞。目录 evidence 应理解为「超出 730 天窗口」，不是「修复已落地」。
