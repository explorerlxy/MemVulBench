# Magma v1.2.1 官方 harness 重放核验

日期：2026-09-17。
对象：HexHive Magma 本地树 `v1.2.1-46-g75d1ae7b`（9 目标、138 个 active canary）。
口径：**只用各目标 `configrc` 的 `PROGRAMS`（21 个官方 harness）**，不做自定义 API driver。
机器结果：`BoostFuzz/benchmarks/bug-catalog/results/magma_v121_official.json`。
回放脚本：`BoostFuzz/benchmarks/bug-catalog/replay_magma_v121_official.py`。

本文件只记录核验结论，不收录 PoC、镜像或日志。

不要把这里的数字和 2026-08-17 那轮混用。那轮把 `/tmp` 自定义 driver 和 UBSan 算进去，得到 `canary_only` 89、`native_crash` 35、`asan_only` 10、`timeout` 4，再合并成 **45/138 可观测**。本轮官方 harness 打得着 canary 的只有 68/138。

## 1. 方法

- 每个 bug 取本地收集的代表性 PoC（优先已知官方配对；`SND024` 与 `SND007` 共用 `SND007_024.flac`）。
- 同一输入分别打 native 与 ASan 构建；用 `MAGMA_STORAGE` 读 canary。
- `native_crash`：进程死于信号（`rc < 0` 或 `rc >= 128`）。普通非零退出不算。
- ASan 指纹：stderr 出现 `ERROR: AddressSanitizer`、`SUMMARY: AddressSanitizer` 或 `AddressSanitizer failed to allocate`。**不含 UBSan。**
- `canary_only`：官方 harness 触发了对应 canary，但 native 不崩、ASan 无报告。
- `official_no_trigger`：21 个官方入口都打不着该 canary（上一轮往往靠自定义 driver）。
- 超时约 12 s（个别 20 s）。

类型标签：论文 Table A1（96 条，经 `AAH*`/`JCH*`/`MAE*` → `PNG*`/`TIF*`/… 重命名）+ lua / libsndfile / sqlite 的 CVE 标题（42 条，Table A1 之后才进仓库）。

**内存核** = 空间 + 时效（OOB / overflow / underflow / overread / underread / underwrite / UAF / heap corruption）。空指针、纯整数溢出、除零、资源耗尽、XXE、泄漏、类型混淆、未初始化读不算。

## 2. Harness 与 PoC

| 口径 | 数量 |
|---|---:|
| 官方目标 | 9 |
| 官方 harness（`PROGRAMS`） | **21** |
| 论文 Table 2「25 drivers」 | v1.0 表述；v1.0.0 的 `PROGRAMS` 实际是 19（无 lua / libsndfile） |
| 本地 PoC 文件 | **373** |
| 有输入的 bug | **138 / 138** |

| 目标 | 官方 harness | canary | PoC 文件 | 官方能触发 |
|---|---|---:|---:|---:|
| libpng | `libpng_read_fuzzer` | 7 | 15 | 4 |
| libtiff | `tiff_read_rgba_fuzzer`, `tiffcp` | 14 | 23 | 10 |
| libxml2 | `libxml2_xml_read_memory_fuzzer`, `xmllint` | 17 | 77 | 7 |
| poppler | `pdf_fuzzer`, `pdfimages`, `pdftoppm` | 22 | 55 | 13 |
| openssl | `asn1`, `asn1parse`, `bignum`, `server`, `client`, `x509` | 20 | 22 | 5 |
| sqlite3 | `sqlite3_fuzz` | 20 | 99 | 17 |
| php | `json`, `exif`, `unserialize`, `parser` | 16 | 51 | 4 |
| lua | `lua` | 4 | 6 | 4 |
| libsndfile | `sndfile_fuzzer` | 18 | 25 | 4 |
| **合计** | **21** | **138** | **373** | **68** |

Magma 上游不随仓库发布 PoC 套件。上表 PoC 是本地收集（OSF / corpus / mode），不是官方附件。构建树里还有 `tiffinfo`、`sndfile_fuzzer_flac` 等额外二进制，**不计入 21**。

## 3. 漏洞类型

| 归类 | 条数 | 是否内存核 |
|---|---:|---|
| 空间读（OOB read / overread / underread） | 37 | 是 |
| 空间写（overflow / underflow / underwrite / OOB write） | 32 | 是 |
| Use-after-free | 6 | 是 |
| 整数溢出兼内存破坏 | 3 | 是（72 口径排除） |
| 空指针 | 22 | 否 |
| 纯整数溢出 | 11 | 否 |
| 资源耗尽 | 9 | 否 |
| 除零 | 8 | 否 |
| 类型混淆 | 4 | 否 |
| 未初始化读 | 2 | 否 |
| XXE / 逻辑 / 泄漏 | 4 | 否 |
| **合计** | **138** | 内存核 **78** |

细类（论文/CVE 原文，除零两种拼写未合并）：

| 标签 | 条数 |
|---|---:|
| OOB read | 25 |
| Heap buffer overflow | 23 |
| 0-pointer dereference | 22 |
| Integer overflow | 10 |
| Heap buffer overread | 9 |
| Use-after-free | 6 |
| Stack buffer overflow | 5 |
| Divide by zero | 5 |
| Type confusion | 4 |
| Resource exhaustion (memory) | 4 |
| Resource exhaustion (CPU) | 3 |
| Divide-by-zero | 3 |
| Integer overflow, Buffer overflow | 2 |
| OOB write | 2 |
| XML external entity | 2 |
| Stack buffer overread | 2 |
| Uninitialized memory access | 2 |
| 其余各 1 | Integer overflow + divide by zero；Integer overflow + heap corruption；Heap buffer underflow / underwrite；Stack buffer underread；API inconsistency；Memory leak；Resource exhaustion（无修饰）×2 |

**78** 是本轮主数字。若去掉 6 条边界（`PNG005` `SQL019` `XML005` 的整数兼内存，以及 `PDF022` `SSL004` `PHP012` 的 stack over/under-read），得 **72**，与早先「139 里约 72 个内存漏洞」的口径对齐；现行分母是 138。

Table A1 覆盖 96 条（其中内存核 51）；后补 42 条（lua 4 + snd 18 + sqlite 20，其中内存核 27）。

## 4. 内存核的可观测性（78）

包容计数（一条可同时算 native 和 ASan）：

| 现象 | 条数 | 占 78 | ID |
|---|---:|---:|---|
| 能直接 native crash | **7** | 9.0% | `PDF006` `SND001` `SND020` `SSL001` `TIF001` `TIF013` `XML001` |
| 能出 ASan 指纹 | **5** | 6.4% | `SND001`（FPE）`SND005`（global-buffer-overflow）`TIF001` / `TIF013`（heap-buffer-overflow）`XML001`（stack-buffer-overflow） |
| 只有 canary | **29** | 37.2% | 见下 |
| 超时 | 3 | 3.8% | `PDF005` `PHP011` `SQL001` |
| 官方 harness 打不着 | 38 | 48.7% | 需非 `PROGRAMS` 入口 |

互斥分层：

| detect | 条数 |
|---|---:|
| `native_and_asan` | 4 |
| `native_crash` | 3 |
| `asan_only` | 1 |
| `canary_only` | 29 |
| `timeout` | 3 |
| `official_no_trigger` | 38 |

官方 **打得着的 40 条** 内存核：native 7、ASan 5、仅 canary 29、超时 3。大约四分之三仍然只有 canary。

仅 canary（29）：`LUA004` `PDF003` `PDF011` `PDF016` `PDF022` `PHP004` `SND017` `SQL004` `SQL010` `SQL011` `SQL012` `SQL013` `SQL015` `SQL016` `SQL018` `SQL019` `SSL002` `SSL009` `SSL020` `TIF002` `TIF005` `TIF006` `TIF007` `TIF008` `TIF012` `XML009` `XML014` `XML016` `XML017`。

## 5. 全 138 的官方 detect

| detect | 条数 |
|---|---:|
| `official_no_trigger` | 70 |
| `canary_only` | 44 |
| `native_crash` | 14 |
| `native_and_asan` | 5 |
| `timeout` | 4 |
| `asan_only` | 1 |

官方触发 68。包容：native crash 19，ASan 指纹 6。

按目标：

| 目标 | canary | 官方触发 | native / ASan / 仅 canary / 超时 / 打不着 | 内存核 |
|---|---:|---:|---|---:|
| libpng | 7 | 4 | 2 / 0 / 2 / 0 / 3 | 2 |
| libtiff | 14 | 10 | 1+2 / 2 / 7 / 0 / 4 | 10 |
| libxml2 | 17 | 7 | 0+1 / 1 / 6 / 0 / 10 | 13 |
| poppler | 22 | 13 | 5+1 / 1 / 5 / 2 / 9 | 8 |
| openssl | 20 | 5 | 1 / 0 / 4 / 0 / 15 | 5 |
| sqlite3 | 20 | 17 | 2 / 0 / 14 / 1 / 3 | 11 |
| php | 16 | 4 | 0 / 0 / 3 / 1 / 12 | 13 |
| lua | 4 | 4 | 2 / 0 / 2 / 0 / 0 | 1 |
| libsndfile | 18 | 4 | 1+1 / 2 / 1 / 0 / 14 | 15 |

php / openssl / libsndfile 的官方入口覆盖很差：多数 PoC 要 `execute`、内部 SSL API 或 flac/write driver。

## 6. 逐条清单

列：`id` / 目标 / 内存分层 / 官方 detect / 类型。

| id | 目标 | 分层 | detect | 类型 |
|---|---|---|---|---|
| PNG001 | libpng | integer | native_crash | Integer overflow, divide by zero |
| PNG002 | libpng | core_memory | official_no_trigger | Use-after-free |
| PNG003 | libpng | other | canary_only | API inconsistency |
| PNG004 | libpng | integer | official_no_trigger | Integer overflow |
| PNG005 | libpng | core_memory | official_no_trigger | Integer overflow, Buffer overflow |
| PNG006 | libpng | other | canary_only | Memory leak |
| PNG007 | libpng | null_deref | native_crash | 0-pointer dereference |
| SND001 | libsndfile | core_memory | native_and_asan | Heap buffer overflow |
| SND002 | libsndfile | core_memory | official_no_trigger | Heap buffer overflow |
| SND004 | libsndfile | other | official_no_trigger | Divide by zero |
| SND005 | libsndfile | core_memory | asan_only | Heap buffer overflow |
| SND006 | libsndfile | core_memory | official_no_trigger | OOB read |
| SND007 | libsndfile | core_memory | official_no_trigger | OOB read |
| SND010 | libsndfile | core_memory | official_no_trigger | Heap buffer overflow |
| SND012 | libsndfile | core_memory | official_no_trigger | Heap buffer overflow |
| SND013 | libsndfile | core_memory | official_no_trigger | Heap buffer overflow |
| SND014 | libsndfile | other | official_no_trigger | Divide by zero |
| SND015 | libsndfile | core_memory | official_no_trigger | Heap buffer overread |
| SND016 | libsndfile | other | official_no_trigger | Divide by zero |
| SND017 | libsndfile | core_memory | canary_only | Heap buffer overflow |
| SND020 | libsndfile | core_memory | native_crash | Heap buffer overflow |
| SND022 | libsndfile | core_memory | official_no_trigger | Heap buffer overread |
| SND023 | libsndfile | core_memory | official_no_trigger | Heap buffer overread |
| SND024 | libsndfile | core_memory | official_no_trigger | OOB read |
| SND025 | libsndfile | core_memory | official_no_trigger | Heap buffer overflow |
| TIF001 | libtiff | core_memory | native_and_asan | Heap buffer overflow |
| TIF002 | libtiff | core_memory | canary_only | Heap buffer overflow |
| TIF003 | libtiff | other | official_no_trigger | Divide by zero |
| TIF004 | libtiff | other | official_no_trigger | Divide by zero |
| TIF005 | libtiff | core_memory | canary_only | OOB read |
| TIF006 | libtiff | core_memory | canary_only | OOB read |
| TIF007 | libtiff | core_memory | canary_only | OOB read |
| TIF008 | libtiff | core_memory | canary_only | Heap buffer overflow |
| TIF009 | libtiff | null_deref | native_crash | 0-pointer dereference |
| TIF010 | libtiff | core_memory | official_no_trigger | Heap buffer underflow |
| TIF011 | libtiff | core_memory | official_no_trigger | OOB read |
| TIF012 | libtiff | core_memory | canary_only | Heap buffer overflow |
| TIF013 | libtiff | core_memory | native_and_asan | OOB write |
| TIF014 | libtiff | other | canary_only | Resource Exhaustion |
| XML001 | libxml2 | core_memory | native_and_asan | Stack buffer overflow |
| XML002 | libxml2 | typeconf | canary_only | Type confusion |
| XML003 | libxml2 | other | canary_only | XML external entity |
| XML004 | libxml2 | other | official_no_trigger | Resource exhaustion |
| XML005 | libxml2 | core_memory | official_no_trigger | Integer overflow, heap corruption |
| XML006 | libxml2 | core_memory | official_no_trigger | Stack buffer overflow |
| XML007 | libxml2 | core_memory | official_no_trigger | OOB read |
| XML008 | libxml2 | core_memory | official_no_trigger | OOB read |
| XML009 | libxml2 | core_memory | canary_only | OOB read |
| XML010 | libxml2 | other | official_no_trigger | XML external entity |
| XML011 | libxml2 | core_memory | official_no_trigger | Heap buffer overflow |
| XML012 | libxml2 | core_memory | official_no_trigger | Use-after-free |
| XML013 | libxml2 | core_memory | official_no_trigger | Use-after-free |
| XML014 | libxml2 | core_memory | canary_only | Heap buffer overread |
| XML015 | libxml2 | core_memory | official_no_trigger | Heap buffer overread |
| XML016 | libxml2 | core_memory | canary_only | Heap buffer overflow |
| XML017 | libxml2 | core_memory | canary_only | Heap buffer overread |
| LUA001 | lua | integer | native_crash | Integer overflow |
| LUA002 | lua | null_deref | native_crash | 0-pointer dereference |
| LUA003 | lua | integer | canary_only | Integer overflow |
| LUA004 | lua | core_memory | canary_only | OOB read |
| SSL001 | openssl | core_memory | native_crash | OOB read |
| SSL002 | openssl | core_memory | canary_only | Use-after-free |
| SSL003 | openssl | other | canary_only | Resource exhaustion (memory) |
| SSL004 | openssl | core_memory | official_no_trigger | Stack buffer overread |
| SSL005 | openssl | other | official_no_trigger | Resource exhaustion (memory) |
| SSL006 | openssl | integer | official_no_trigger | Integer overflow |
| SSL007 | openssl | integer | official_no_trigger | Integer overflow |
| SSL008 | openssl | null_deref | official_no_trigger | 0-pointer dereference |
| SSL009 | openssl | core_memory | canary_only | OOB read |
| SSL010 | openssl | integer | official_no_trigger | Integer overflow |
| SSL011 | openssl | null_deref | official_no_trigger | 0-pointer dereference |
| SSL012 | openssl | null_deref | official_no_trigger | 0-pointer dereference |
| SSL013 | openssl | null_deref | official_no_trigger | 0-pointer dereference |
| SSL014 | openssl | typeconf | official_no_trigger | Type confusion |
| SSL015 | openssl | null_deref | official_no_trigger | 0-pointer dereference |
| SSL016 | openssl | other | official_no_trigger | Resource exhaustion (CPU) |
| SSL017 | openssl | null_deref | official_no_trigger | 0-pointer dereference |
| SSL018 | openssl | other | official_no_trigger | Resource exhaustion (memory) |
| SSL019 | openssl | other | official_no_trigger | Resource exhaustion (CPU) |
| SSL020 | openssl | core_memory | canary_only | OOB read |
| PHP001 | php | core_memory | official_no_trigger | Heap buffer overread |
| PHP002 | php | uninit | canary_only | Uninitialized memory access |
| PHP003 | php | core_memory | official_no_trigger | OOB read |
| PHP004 | php | core_memory | canary_only | OOB read |
| PHP005 | php | core_memory | official_no_trigger | OOB read |
| PHP006 | php | core_memory | official_no_trigger | Heap buffer overflow |
| PHP007 | php | core_memory | official_no_trigger | OOB read |
| PHP008 | php | core_memory | official_no_trigger | OOB read |
| PHP009 | php | uninit | canary_only | Uninitialized memory access |
| PHP010 | php | core_memory | official_no_trigger | OOB read |
| PHP011 | php | core_memory | timeout | Heap buffer overread |
| PHP012 | php | core_memory | official_no_trigger | Stack buffer underread |
| PHP013 | php | core_memory | official_no_trigger | Stack buffer overflow |
| PHP014 | php | core_memory | official_no_trigger | OOB write |
| PHP015 | php | integer | official_no_trigger | Integer overflow |
| PHP016 | php | core_memory | official_no_trigger | OOB read |
| PDF001 | poppler | other | official_no_trigger | Divide-by-zero |
| PDF002 | poppler | other | native_and_asan | Resource exhaustion (memory) |
| PDF003 | poppler | core_memory | canary_only | Stack buffer overflow |
| PDF004 | poppler | null_deref | official_no_trigger | 0-pointer dereference |
| PDF005 | poppler | core_memory | timeout | Heap buffer overread |
| PDF006 | poppler | core_memory | native_crash | Heap buffer overflow |
| PDF007 | poppler | core_memory | official_no_trigger | Heap buffer underwrite |
| PDF008 | poppler | other | native_crash | Divide-by-zero |
| PDF009 | poppler | integer | timeout | Integer overflow |
| PDF010 | poppler | null_deref | native_crash | 0-pointer dereference |
| PDF011 | poppler | core_memory | canary_only | Heap buffer overflow |
| PDF012 | poppler | integer | canary_only | Integer overflow |
| PDF013 | poppler | typeconf | official_no_trigger | Type confusion |
| PDF014 | poppler | null_deref | official_no_trigger | 0-pointer dereference |
| PDF015 | poppler | typeconf | official_no_trigger | Type confusion |
| PDF016 | poppler | core_memory | canary_only | OOB read |
| PDF017 | poppler | core_memory | official_no_trigger | Stack buffer overflow |
| PDF018 | poppler | null_deref | native_crash | 0-pointer dereference |
| PDF019 | poppler | integer | official_no_trigger | Integer overflow |
| PDF020 | poppler | other | official_no_trigger | Resource exhaustion (CPU) |
| PDF021 | poppler | other | native_crash | Divide-by-zero |
| PDF022 | poppler | core_memory | canary_only | Stack buffer overread |
| SQL001 | sqlite3 | core_memory | timeout | Heap buffer overflow |
| SQL002 | sqlite3 | null_deref | canary_only | 0-pointer dereference |
| SQL003 | sqlite3 | null_deref | native_crash | 0-pointer dereference |
| SQL004 | sqlite3 | core_memory | canary_only | OOB read |
| SQL005 | sqlite3 | null_deref | canary_only | 0-pointer dereference |
| SQL006 | sqlite3 | null_deref | native_crash | 0-pointer dereference |
| SQL007 | sqlite3 | null_deref | canary_only | 0-pointer dereference |
| SQL008 | sqlite3 | null_deref | official_no_trigger | 0-pointer dereference |
| SQL009 | sqlite3 | core_memory | official_no_trigger | Heap buffer overflow |
| SQL010 | sqlite3 | core_memory | canary_only | Heap buffer overflow |
| SQL011 | sqlite3 | core_memory | canary_only | Heap buffer overflow |
| SQL012 | sqlite3 | core_memory | canary_only | OOB read |
| SQL013 | sqlite3 | core_memory | canary_only | Heap buffer overflow |
| SQL014 | sqlite3 | null_deref | canary_only | 0-pointer dereference |
| SQL015 | sqlite3 | core_memory | canary_only | Use-after-free |
| SQL016 | sqlite3 | core_memory | canary_only | Use-after-free |
| SQL017 | sqlite3 | null_deref | official_no_trigger | 0-pointer dereference |
| SQL018 | sqlite3 | core_memory | canary_only | OOB read |
| SQL019 | sqlite3 | core_memory | canary_only | Integer overflow, Buffer overflow |
| SQL020 | sqlite3 | null_deref | canary_only | 0-pointer dereference |

## 7. 引用时注意

1. 对外写 Magma 可观测性，先声明口径：官方 21 harness，还是「能触发 canary 的任意入口」。
2. 不要用本轮 7/5/29 去改 `docs/design.md` 里的 45/138，除非同时改掉那一轮的自定义-driver 前提。
3. 78 与 72 不要混写。78 = 空间+时效（含 6 条边界）；72 = 去掉这 6 条。
4. 论文「25 drivers」不是 v1.2.1 的 `PROGRAMS` 计数。
