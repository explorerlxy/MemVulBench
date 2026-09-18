# Benchmark 构建进展

> 最近核验：2026-09-18 11:20（Asia/Shanghai）
> 事实来源：`data/measure/manual/`（回放）与 `data/measure/downloads/`（下载）
> `known_real` 已改为 expected 之外的 unique 漏洞，见 [known-real.md](known-real.md)

## 正式 20 席（2026-09-18 替换后）

2026-09-17 操作员按最终入口五元组准入 20 个正式席；
**2026-09-18 arrow 经最终入口复验后替换 librawspeed**（见下节），
`catalog_admission=admitted`。
已核验已知内存漏洞 **292**（expected 287 + 额外 5）。
现行决定见 `data/measure/admission/2026-09-18.json`（取代 2026-09-17）。
正式材料在 `targets/<project>/{pocs,images,logs}`。

纳入 **espeak-ng**（identity `ssml-fuzzer`，10 unique）与 **ndpi**
（identity-on-densest `fuzz_process_packet`，15 unique）。
2026-09-16 曾从评测集放出 **arrow** 与 **lwan**（均门禁刚好 8，prefix 文法不齐）：
材料迁到 `targets/archived/{arrow,lwan}/`，measure 记 `benchmark_seat=archived`。
2026-09-18 arrow 复席，librawspeed（7 个五元组，6–7 暂缓带）让位归档。

| 正式席 | 方法 | 可验证 |
|---|---|---:|
| ghostpdl | identity gstoraster | 35 |
| gpac | prefix %3 | 27 |
| assimp | identity | 26 |
| PcapPlusPlus | prefix %4 | 18 |
| ndpi | identity-on-densest | 15 |
| opensc | prefix %3 | 15 |
| openh264 | identity decoder | 14 |
| libdwarf | prefix %10 | 14 |
| upx | prefix %3 | 13 |
| selinux | identity secilc | 13 |
| hdf5 | prefix %2 | 12 |
| fluent-bit | prefix %6 | 12 |
| openvswitch | prefix %6 | 12 |
| pcl | identity ply_reader | 12 |
| sleuthkit | prefix %6 | 11 |
| libavc | identity svc_dec | 11 |
| espeak-ng | identity ssml-fuzzer | 10 |
| libxml2 | prefix %3 | 9 |
| libraw | identity | 8 |
| arrow | prefix %3 | 8 |

可验证合计 **295**。另归档：lwan（8）、librawspeed（7，2026-09-18 被替换）。binutils-gdb 仍因文法过散不进集。
hunspell / lcms 暂缓，openthread 直接 pass，php-src 暂缓（6）。

## 2026-09-18 替换核验：arrow 入，librawspeed 出

librawspeed 的 7 个五元组处于 6–7 暂缓带，仅靠 2026-09-17 明确复核入集；
arrow 归档时即为 7 expected + 1 known_real = 8（门禁线，无需特批），且证据链完整
（逐 PoC 日志与聚合日志均已持久化；lwan 原始日志已丢失，5/8 指纹依赖后补 harness，故未选）。

本次操作员复验（逐条人工执行）：

- `docker load targets/arrow/images/arrow-8b09ecc-agg.tar`（sha256 `6274a5aa…` 与记录一致）。
- 容器内核对：`SOURCE=8b09ecc5c690dd270dea83490f292c2e00eef75b`；
  `/out/arrow_agg_fuzzer` sha256 `dcff9712…`、`/work/agg/arrow_agg_fuzzer.cc` sha256 `bf07a122…` 均与账本一致。
- 9 个聚合 PoC（prefix %3）逐一回放，`abort_on_error=1:symbolize=1:detect_leaks=0`，9/9 exit 134；
  parser 签名与 2026-09-15 已审计聚合日志**严格相等**（0 例 operator 裁决）。
- 唯一五元组 8：heap-OOB×5（Visit validate.cc:380 R、UnionType type.cc:341 W、
  GetBit bit_util.h:428 R、value_offset array.h:589 R、CountSetBits bit_util.cc:95 R）、
  global-OOB×2（Visit validate.cc:358 R、WriteRingBuffer decode.c:1274 W）、
  negative-size-param×1（BitReader bit_stream_utils.h:110；42504313/42504668 同指纹碰撞）。
- 账本落库：`data/measure/rereplay/2026-09-18/{arrow.json,index.json}`；
  日志持久化 `targets/arrow/logs/8b09ecc-agg-rereplay-20260918/`（9 条）。
- 材料迁移：arrow 回 `targets/arrow/`，librawspeed 迁 `targets/archived/librawspeed/`。
- 准入：`data/measure/admission/2026-09-18.json`；证据账本同步（301 条观测：300 故障 + 1 clean）。
  类型分布：heap-buffer-overflow 187、global-buffer-overflow 19、negative-size-param 6，
  use-after-poison 归零（原 4 条全来自 librawspeed）。
- 容器已卸。

## 总体状态

已完成前台人工编译、逐条 PoC 回放和结果记录的项目：**37 个**（含夜间补测）。
密度门槛 unique expected + unique known_real ≥ 8 的达标战役曾有 22 个；
正式评测集取其中 **20** 席（上表）。**binutils-gdb** 因 harness 过散
（12 入口 / 3 种文法）退出聚合评测集，**skia** 同样不进聚合（densest latent 6）。
`catalog_admission` 在 2026-09-17 对正式 20 席翻为 `admitted`；未入选集的测量项目仍为 `pending_manual_review`。
前台改为按项目做 harness 聚合（并集或选择前缀；包装器编进覆盖图），
逐条核对调整后 expected PoC 的指纹，通过后再 persist 新 tar。
hdf5 聚合已过验收并 persist：`targets/hdf5/images/hdf5-bd7616-agg.tar`
（sha256 2312c653…），12/12 expected 指纹匹配。upx 聚合已过验收并 persist：
`targets/upx/images/upx-09c5e383-agg.tar`（sha256 163b730b…），14/14
expected 与原始回放日志 parser 指纹一致（prefix %3：test/list/decompress）。
`targets/upx/pocs/agg/` 为加选择前缀后的 PoC。sleuthkit 聚合已过验收并 persist：
`targets/sleuthkit/images/sleuthkit-5eabe4d5-agg.tar`（sha256 1b3ab039…），
11/11 expected 与原始回放日志 parser 指纹一致（prefix %6：ext/hfs/ntfs/iso/fat/apfs）。
容器已卸。PcapPlusPlus 聚合已过验收并 persist：
`targets/PcapPlusPlus/images/PcapPlusPlus-65974d7-agg.tar`（sha256 2347257a…），
18/18 expected 同一崩溃位点（prefix %4：FuzzTarget / Coverage / Ng / WriterNg）。
容器已卸。arrow 聚合曾过验收并 persist，**2026-09-16 放出正式席**：
`targets/arrow/images/arrow-8b09ecc-agg.tar`（sha256 6274a5aa…；2026-09-18 复席后路径），
7/7 expected + 1 unique known_real（prefix %3：ipc-file / ipc-stream / parquet）。
42481229 仍是 CountSetBits/GetNullCount 走，ASan 类从 SEGV 漂到 GetBit。
容器已卸。libraw 四个 OSS-Fuzz 名是同一份 `libraw_fuzzer.cc`（四份
manual 二进制 sha256 相同），不做假前缀。覆盖图版 identity 二进制已 persist：
`targets/libraw/images/libraw-371161a-agg.tar`（sha256 37b0a375…），8/8 expected
与原始回放日志一致。容器已卸。librawspeed 聚合已过验收并 persist：
`targets/archived/librawspeed/images/librawspeed-a177914-agg.tar`（sha256 23b68d4a…；2026-09-18 替换后归档），
8/8 expected 与原始回放同一走（prefix %6：Srw/Dng/Nef/Fiff/Raw/Tiff）。
42508774 原始日志 #0 已是 OffsetPerRowOrCol::apply（无行号时 parse 落到 applyOpCodes）；
聚合版带行号，parse 报 apply。容器已卸。libxml2 聚合已过验收并 persist：
`targets/libxml2/images/libxml2-4b3452d-agg.tar`（sha256 4d547db5…），
9/9 expected 与原始回放日志 parser 指纹一致（prefix %3：html/xinclude/schema）。
容器已卸。fluent-bit 聚合已过验收并 persist：
`targets/fluent-bit/images/fluent-bit-e5289e606-agg.tar`（sha256 bc0a0dba…），
12/12 expected 与原始回放日志 parser 指纹一致（prefix %6：parser/gelf/msgpack/utils/config_map/strp）。
容器已卸。lwan 聚合曾过验收并 persist，**2026-09-16 放出正式席**：
`targets/archived/lwan/images/lwan-341dca6-agg.tar`（sha256 93831dbc…），
8/8 expected（prefix %4：request/config/template/h2）。后出 harness
对象来自 complete 镜像里已核过的 .o（<stdin> 文件名，parse 会跳过该帧）。
容器已卸。openvswitch 聚合已过验收并 persist：
`targets/openvswitch/images/openvswitch-f5129153-agg.tar`（sha256 79de11d6…），
12/12 expected 与原始回放日志 parser 指纹一致（prefix %6：flow/ofp/odp/ofctl/preleak/expr）。
ofp 两个名字同一源。库是镜像里最后一次 NDEBUG ASan remake。容器已卸。gpac 聚合已过验收并 persist：
`targets/gpac/images/gpac-b890f1c-agg.tar`（sha256 e15c2cd6…），
29/29 expected 同一走（prefix %3：parse/probe/m2ts）。fuzz_route 无 expected。
容器已卸。libdwarf 聚合已过验收并 persist：
`targets/libdwarf/images/libdwarf-2ee326ba-agg.tar`（sha256 cf5a6621…），
14/14 expected 与原始回放日志 parser 指纹一致（prefix %10：attrs/offset/globals/macro/srcfiles/frame/loclist/stack/find/print）。
383170474 仍缺。容器已卸。opensc 聚合已过验收并 persist：
`targets/opensc/images/opensc-2c9dddc-agg.tar`（sha256 ecce00b2…），
15/15 expected 与原始回放日志 parser 指纹一致（prefix %3：pkcs15init/card/encode）。
后出 pkcs11/crypt/tool 不在 2c9dddc 树内。42509841 unmatched 不进 persist。
容器已卸。libavc 覆盖图版 identity 已 persist：
`targets/libavc/images/libavc-764ab7b-agg.tar`（sha256 a3d36d4c…），
10/10 expected + 2/2 known_real 与原始回放日志 parser 指纹一致（仅 svc_dec_fuzzer，无前缀）。
容器已卸。assimp 覆盖图版 identity 已 persist：
`targets/assimp/images/assimp-d34cd103-agg.tar`（sha256 68a4dde4…），
26/26 expected 与原始回放日志 parser 指纹一致（单 harness，无前缀）。
容器已卸。selinux 覆盖图版 identity 已 persist：
`targets/selinux/images/selinux-38a09b74-agg.tar`（sha256 c0b0eb4b…），
13/13 expected 与原始回放日志 parser 指纹一致（仅 secilc-fuzzer，无前缀）。
容器已卸。ghostpdl 覆盖图版 identity 已 persist：
`targets/ghostpdl/images/ghostpdl-991a95ff-agg.tar`（sha256 1cc8dca8…），
34/34 expected + 1/1 unique known_real 与原始回放日志 parser 指纹一致（仅 gstoraster，无前缀）。
容器已卸。pcl 覆盖图版 identity 已 persist：
`targets/pcl/images/pcl-09e914b0-agg.tar`（sha256 359cc2c8…），
12/12 expected 与目录 catalog_signature 一致（原始 /tmp 日志已丢；JSON 函数名被人工缩短）。
openh264 identity persist：`targets/openh264/images/openh264-83a0eae9-agg.tar`
（sha256 bc345f93…），12/12 + 2 known_real。**正式席。**
espeak-ng identity persist：`targets/espeak-ng/images/espeak-ng-ccb1c31-agg.tar`
（sha256 b1253b14…），10/11 expected（42508338 LoadVoice 未出）。**正式席。**
ndpi identity-on-densest persist：`targets/ndpi/images/ndpi-65d526d8-agg.tar`
（sha256 caff1436…），15/20 expected（仅 fuzz_process_packet；5 条后期 latent 未出）。**正式席。**
skia `skipped_operator`。hunspell identity persist：`targets/hunspell/images/hunspell-6291cac8-agg.tar`
（sha256 943b67a2…），6/8 ID（5 unique expected + 2 known_real = 7，暂缓）。
openthread / lcms 已 persist，分别直接 pass / 暂缓。

## 聚合战役镜像（早验收）

当时 `catalog_admission` 尚未翻转；2026-09-17 已按最终入口五元组准入。当时指纹对照为 parser `kind+access+func+file`。
prefix 项目的 PoC 在 `targets/<p>/pocs/agg/` 加了 1 字节选择前缀；identity 项目为原字节拷贝。

| 项目 | 方法 | expected | known_real | 包装器 |
|---|---|---:|---:|---|
| ghostpdl | identity | 34/34 | 1/1 | gstoraster |
| gpac | prefix %3 | 29/29 | — | parse/probe/m2ts |
| assimp | identity | 26/26 | — | assimp_fuzzer |
| PcapPlusPlus | prefix %4 | 18/18 | — | FuzzTarget/Coverage/Ng/WriterNg |
| opensc | prefix %3 | 15/15 | — | pkcs15init/card/encode |
| upx | prefix %3 | 14/14 | — | test/list/decompress |
| libdwarf | prefix %10 | 14/14 | — | attrs/offset/globals/macro/src/frame/loclist/stack/find/print |
| selinux | identity | 13/13 | — | secilc |
| openh264 | identity | 12/12 | 2/2 | decoder_fuzzer |
| espeak-ng | identity | 10/11 | — | ssml-fuzzer |
| ndpi | identity-on-densest | 15/20 | — | fuzz_process_packet |
| hunspell | identity | 6/8 | 2/2 | affdicfuzzer |
| openthread | prefix %2 | 4/14 | — | ip6-send / radio-receive |
| lcms | prefix %3 | 7/11 | — | profile / transform_all / IT8 |
| hdf5 | prefix %2 | 12/12 | — | h5_read/h5_extended |
| fluent-bit | prefix %6 | 12/12 | — | parser/gelf/msgpack/utils/config_map/strp |
| openvswitch | prefix %6 | 12/12 | — | flow/ofp/odp/ofctl/preleak/expr |
| pcl | identity | 12/12 | — | ply_reader |
| sleuthkit | prefix %6 | 11/11 | — | ext/hfs/ntfs/iso/fat/apfs |
| libavc | identity | 10/10 | 2/2 | svc_dec |
| libxml2 | prefix %3 | 9/9 | — | html/xinclude/schema |
| libraw | identity | 8/8 | — | libraw_fuzzer |
| arrow | prefix %3 | 7/7 | 1 unique / 2 PoC | **2026-09-18 复席**（替换 librawspeed）；ipc-file / ipc-stream / parquet |

归档（达标但未入正式席，材料在 `targets/archived/`）：

| 项目 | 方法 | expected | known_real | 放出原因 |
|---|---|---:|---:|---|
| librawspeed | prefix %6 | 8/8* | — | 2026-09-18 被 arrow 替换；最终入口唯一五元组 7（6–7 暂缓带） |
| lwan | prefix %4 | 8/8 | — | 门禁刚好 8；request/config/template/h2 异文法 |

本轮（2026-09-15）新完成 **binutils-gdb** `7a53275`（78/78，10 unique expected）、
**libxml2** `4b3452d`（54/54，9）、**opensc** `2c9dddc`（76/76，15）、
**harfbuzz** `a268068`（54/54，3；不足 6，直接 pass）、
**php-src** `e5b6f43`（27/27，6 unique expected；6–7 暂缓）、
**fluent-bit** `e5289e606`（34/34，12 unique expected；达标）、
**open62541** `23131fe8`（27/27，2 unique expected；不足 6，直接 pass）、
**serenity** `84996c6567`（35/35，4 unique expected；不足 6，直接 pass）、
**librawspeed** `a17791452ef3`（21/21，8 unique expected；达标）、
**libdwarf** `2ee326ba`（24/25，14 unique expected；达标；缺 383170474）、
**selinux** `38a09b74`（20/20，13 unique expected；达标）、
**assimp** `d34cd103`（40/40，26 unique expected；达标）、
**openh264** `83a0eae9`（24/24，12 unique expected + 2 known_real；达标；补第 20 席）。

## 已完成前台项目

`known_real` 列为 unique 漏洞数（不是 PoC）。`PoC` 列为已回放 / 目录应有。
`可验证` = 去重 expected + unique known_real。

| 项目 | PoC | expected | unique | known_real | 可验证 | clean | leak | 其他 | 基线 / 说明 |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| ghostpdl | 90/90 | 34 | 34 | 1 | 35 | 34 | 0 | 21 collide | `991a95ff`；42514830 为零页 SEGV；identity agg persist |
| gpac | 49/49 | 29 | 27 | 0 | 27 | 20 | 0 | — | 工作镜像已 persist；agg persist |
| PcapPlusPlus | 20/20 | 18 | 18 | 0 | 18 | 2 | 0 | — | 工作镜像已 persist；agg persist |
| opensc | 76/76 | 15 | 15 | 0 | 15 | 60 | 0 | 1 unmatched | `2c9dddc`；42509841 SEGV 未闭环；agg persist |
| upx | 16/16 | 14 | 13 | 0 | 13 | 2 | 0 | — | 7 条同洞漂移仍算 expected；agg persist |
| openh264 | 24/24 | 12 | 12 | 2 | 14 | 8 | 0 | 1 collide + 1 unmatched | `83a0eae9`；identity agg persist。42491572 / 42493060 为 expected 外 unique |
| espeak-ng | 12/12 | 11 | 10 | 0 | 10 | 2 | 0 | 42508338 未出 | `ccb1c31`；identity agg persist。**正式席** |
| ndpi | 37/69 | 20 | 15 | 0 | 15 | 21 | 0 | 1 collide；reader 未回放 | `65d526d8`；identity-on-densest agg persist。**正式席**。42481886/42483342/42487587/42492641/42497205 未出 |
| hunspell | 16/16 | 8 | 5 | 2 | 7 | 7 | 0 | 1 collide | `6291cac8`；identity agg persist。6–7 暂缓。42516014 撞 42516007；42518895/42516081 为 unique known_real |
| openthread | 21/34 | 14 | 4 | 0 | 4 | 17 | 0 | ncp/cli 基线不在树 | `639b58ea`；prefix %2 agg persist。直接 pass。仅 2018-02-02 wave 4 条出 |
| lcms | 13/17 | 11 | 7 | 0 | 7 | 6 | 0 | postscript/universal/virtual 不在树 | `3d3001f0`；prefix %3 agg persist。6–7 暂缓 |
| hdf5 | 14/14 | 12 | 12 | 0 | 12 | 2 | 0 | — | 工作镜像已 persist；agg persist |
| libdwarf | 24/25 | 14 | 14 | 0 | 14 | 9 | 0 | 1 collide + 缺 1 PoC | `2ee326ba`；wave 2/2。13 个 harness 均在树内。42522668 撞上 dietype_offset；agg persist |
| assimp | 40/40 | 26 | 26 | 0 | 26 | 9 | 0 | 2 collide + 3 unmatched | `d34cd103`；单 harness。5 条同洞漂移仍算 expected；identity agg persist |
| selinux | 20/20 | 13 | 13 | 0 | 13 | 6 | 0 | 1 collide | `38a09b74`；secilc 13 条 exact。42493388 撞上 cil_list_destroy。binpolicy 缺；identity agg persist |
| fluent-bit | 34/34 | 12 | 12 | 0 | 12 | 19 | 0 | 3 collide | `e5289e606`；wave-eve 5/5。3 条 utils 先死在 `flb_hash_get_by_id`；agg persist |
| openvswitch | 13/13 | 12 | 12 | 0 | 12 | 1 | 0 | — | `f5129153`；agg persist |
| pcl | 13/13 | 12 | 12 | 0 | 12 | 1 | 0 | — | 工作镜像已 persist；identity agg persist |
| sleuthkit | 17/17 | 11 | 11 | 0 | 11 | 5 | 0 | 1 earlier abort | 42534995 同走更早 malloc；agg persist |
| libavc | 30/30 | 10 | 10 | 1 | 11 | 18 | 0 | — | 空分派 SEGV，未到目录 heap-overflow；identity agg persist |
| binutils-gdb | 78/78 | 10 | 10 | 0 | 10 | 55 | 0 | 3 collide + 2 unmatched + 1 site_absent | **退出聚合集**：12 harness / 3 文法，不适合整库战役 |
| libxml2 | 54/54 | 9 | 9 | 0 | 9 | 45 | 0 | — | `4b3452d`；18 条后出 harness 用 xml_manual 诊断；agg persist |
| libraw | 16/16 | 8 | 8 | 0 | 8 | 8 | 0 | — | 同洞 SEGV 漂移仍算 expected；identity agg persist |
| librawspeed | 21/21 | 8 | 8 | 0 | 8 | 12 | 0 | 1 collide | `a17791452ef3`；wave-eve 3/3。42517687 先死在 applyOpCodes；agg persist。**2026-09-18 被替换归档**（最终入口唯一五元组 7） |
| lwan | 12/12 | 8 | 8 | 0 | 8 | 3 | 1 | — | **已归档** `targets/archived/lwan/`；不进正式席 |
| arrow | 27/27 | 7 | 7 | 1 | 8 | 15 | 0 | 3 unmatched | **2026-09-18 复席**（替换 librawspeed）；7+1=8；2026-09-18 复验 9/9 严格匹配 |
| php-src | 27/27 | 6 | 6 | 0 | 6 | 20 | 0 | 1 unmatched | `e5b6f43`；6–7 暂缓。wave UAR 未出；JIT harness 缺 |
| serenity | 35/35 | 4 | 4 | 0 | 4 | 26 | 0 | 3 collide + 1 unmatched + 1 timeout | `84996c6567`；ICO Vector 3 条碰撞 |
| pcre2 | 16/16 | 4 | 4 | 0 | 4 | 12 | 0 | — | `69fee50e`；不足门槛 |
| harfbuzz | 54/54 | 3 | 3 | 0 | 3 | 49 | 0 | 2 collide | `a268068`；仅 wave-eve 3 条，直接 pass |
| libredwg | 39/39 | 3 | 3 | 0 | 3 | 28 | 6 | 2 unmatched | 工作镜像已 persist |
| mupdf | 20/20 | 3 | 3 | 0 | 3 | 1 | 16 | — | 工作镜像已 persist |
| radare2 | 25/25 | 3 | 3 | 0 | 3 | 0 | 22 | — | 工作镜像已 persist |
| open62541 | 27/27 | 2 | 2 | 0 | 2 | 25 | 0 | — | `23131fe8`；仅 wave 2 条。后出 json/tcp harness 缺 |
| mruby | 29/29 | 3 | 2 | 0 | 2 | 25 | 0 | 1 OOM | 401868632 是 range_num_to_a 分配器第一现场 |
| c-blosc2 | 37/37 | 2 | 2 | 0 | 2 | 34 | 0 | 1 unmatched | 工作镜像已 persist |
| libjxl | 19/23 | 2 | 2 | 0 | 2 | 17 | 0 | 缺 4 PoC | `35ad5de7`；下载标记 `blocked_missing_poc` |

## 下载与待处理队列

正式 20 席已按 2026-09-16 评选落地。下载器空闲。ffmpeg / imagemagick / gdal 仍不自动重试。

### 第 20 席目录预筛（已结算，不翻 admission）

`n_latent` 是考古提交上的上限；最终仍以 unique expected 指纹 + known_real ≥ 8 为准。
skia / wolfssl / icu 按 binutils 同款「文法过散」处理：整库不聚合。
skia densest 单独 identity 也只有 6 个 latent，不够席位。

| 项目 | 目录预判 | 最密 harness（latent / unique） | 计划 |
|---|---|---|---|
| openh264 | identity | decoder_fuzzer 12 / 12 | **已 persist，进聚合集** |
| espeak-ng | identity | ssml-fuzzer 11 / 11 | **已 persist，10/11，正式席** |
| ndpi | identity-on-densest | fuzz_process_packet 20 / 20 | **已 persist，15/20，正式席** |
| hunspell | identity | affdicfuzzer 8 / 8 | **已 persist，6/8 ID（5 unique + 2 KR = 7），暂缓** |
| openthread | prefix %2 | 基线上仅 ip6+radio；4 / 14 | **已 persist，4 unique，直接 pass** |
| lcms | prefix %3 | 基线上 profile+transform_all+IT8；7 / 11 | **已 persist，7 unique，暂缓** |
| skia | **退出聚合** | api_mock_gpu_canvas 6 / 6 | 约 20 harness / 多文法；材料可归档，不开战 |
| wolfssl | 大概率退出 | densest 3 | 先下，不优先编译 |
| libvips | 大概率不足 | densest 5 | 先下，不编译 |
| icu | 退出 | densest 2 | 先下，不编译 |
| wireshark | identity-on-densest | fuzzshark_ip_proto-udp 14 / 14 | **PoC 阻断**。61/61 首层 >1G，`blocked_missing_poc`。不编译 |

| 状态 | 项目 | PoC | 说明 |
|---|---|---:|---|
| 前台完成 | php-src | 27/27 | measure 已写；6 unique，暂缓。镜像已卸 |
| 前台完成 | fluent-bit | 34/34 | measure 已写；12 unique，达标。镜像已卸 |
| 前台完成 | open62541 | 27/27 | measure 已写；2 unique，直接 pass。镜像已卸 |
| 前台完成 | serenity | 35/35 | measure 已写；4 unique，直接 pass。镜像已卸 |
| 前台完成 | librawspeed | 21/21 | measure 已写；8 unique，达标。镜像已卸 |
| 前台完成 | libdwarf | 24/25 | measure 已写；14 unique，达标。缺 383170474。镜像已卸 |
| 前台完成 | selinux | 20/20 | measure 已写；13 unique，达标。镜像已卸 |
| 前台完成 | assimp | 40/40 | measure 已写；26 unique，达标。镜像已卸 |
| 前台完成 | openh264 | 24/24 | measure 已写；12 unique + 2 known_real，达标。agg persist。镜像已卸 |
| 前台完成 | espeak-ng | 12/12 | measure 已写；10 unique，**正式席**。agg persist。镜像已卸 |
| 前台完成 | ndpi | 69/69 | measure 已写；15 unique expected，**正式席**。agg persist。镜像已卸 |
| 前台完成 | hunspell | 16/16 | measure 已写；5 unique expected + 2 known_real = 7，暂缓。agg persist。镜像已卸 |
| 前台完成 | openthread | 21/34 | measure 已写；4 unique，直接 pass。prefix %2。镜像已卸。ncp/cli 基线不在树内 |
| 前台完成 | lcms | 13/17 | measure 已写；7 unique，暂缓。prefix %3。镜像已卸 |
| 下载完成 | libvips | 18/18 | `ok` attempt 2。eve 镜像 `42496964-vul.tar` 5.2G；旧档 `42477278-vul.tar` 2.7G。层已卸。densest 5，不编译 |
| 下载完成 | wolfssl | 29/29 | `ok`。镜像 `42491298-vul.tar` 5.3G，层已卸。densest 3，不编译 |
| 下载完成 | icu | 14/14 | `ok`。镜像 `42527280-vul.tar` 5.9G，层已卸。densest 2，不编译 |
| 阻断 | wireshark | 0/61 | `blocked_missing_poc`。61 条均首层 >1G，未见 tmp/poc。densest 14，不编译、不重试本策略 |
| 操作员跳过 | skia | 29 已归档 | `skipped_operator`。文法过散，densest latent 6。不拉镜像、不聚合 |
| 操作员跳过 | gdal | 25/147 | `skipped_operator`。不进本轮前台 |
| 阻断 | imagemagick | 13/109 | `blocked_missing_poc`；镜像 `42518438-vul.tar` 已归档 |
| 阻断 | ffmpeg | 0/209 | `poc_failed`。Hub 429，13 次；勿重试直至冷却 |
| 缺 PoC | libjxl | 19/23 | 前台已回放 19；缺 42513614、42515434、42531670、42536925 |

Clash 混合端口 `127.0.0.1:17891`。前台工作容器用完必须立刻从 dockerd 卸下。

## 持久化约束

正式 20 席的 PoC、镜像和回放日志在 `targets/<project>/{pocs,images,logs}`。
arrow 于 2026-09-18 复席 `targets/arrow/`；librawspeed 迁至 `targets/archived/librawspeed/`；
lwan 仍在 `targets/archived/lwan/`。
hunspell / lcms（暂缓）与 openthread（pass）仍在 `targets/<project>/`，不计入正式席。
binutils-gdb 材料仍在 `targets/binutils-gdb/`，但不进入聚合评测。
`.gitignore` 已排除 `targets/`。
其余项目仍在 `/media/hahafish/Data/ForUbuntu/arvo-pocs/`、
`arvo-images/`、`arvo-replay-logs/`。下载临时目录使用 `/tmp/memvul/`。
编译与回放仍坚持人工逐命令执行。
前台工作容器用完必须立刻 `docker commit` + `docker save` 到 Data 盘，再
`docker rm` / `docker rmi`，避免 overlay 占满根分区（约 86G）。
