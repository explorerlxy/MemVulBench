# MemVulBench 考古目录

ARVO 核心内存漏洞去重崩溃点 **> 10** 的全部项目。
每行的基线是该项目上**天然潜伏数量最多**的上游 commit。
口径见 [docs/catalog.md](../docs/catalog.md)。

项目数：64　其中已解析基线：63　潜伏合计：1190　已实测：20

| 项目 | 崩溃点 | 基线 | 日期 | 潜伏 | 波规模 | 方法 |
|---|---:|---|---|---:|---:|---|
| [ffmpeg](ffmpeg/target.yaml) | 212 | `98b122cdb9ef` | 2019-07-07 | 105 | 3 | wave_eve |
| [gdal](gdal/target.yaml) | 160 | `be4b2840cab8` | 2017-05-14 | 131 | 3 | wave_eve |
| [imagemagick](imagemagick/target.yaml) | 121 | `b48da02fb6d3` | 2018-01-20 | 60 | 3 | wave_eve |
| [ghostpdl](ghostpdl/target.yaml) | 92 | `991a95ff4c4f` | 2021-12-14 | 74 | 10 | wave_eve |
| [opensc](opensc/target.yaml) | 86 | `2c9dddc7386d` | 2022-04-14 | 34 | 3 | wave_eve |
| [binutils-gdb](binutils-gdb/target.yaml) | 79 | `7a53275579e7` | 2021-11-18 | 31 | 2 | wave_eve |
| [ndpi](ndpi/target.yaml) | 74 | `65d526d8f6ae` | 2019-12-09 | 31 | 2 | wave_eve |
| [wireshark](wireshark/target.yaml) | 66 | `19c45892461d` | 2018-05-14 | 23 | 2 | wave_eve |
| [skia](skia/target.yaml) | 60 | `86a114685267` | 2018-02-22 | 26 | 2 | wave_eve |
| [harfbuzz](harfbuzz/target.yaml) | 55 | `a26806801005` | 2018-08-26 | 29 | 3 | wave_eve |
| [libxml2](libxml2/target.yaml) | 54 | `4b3452d17123` | 2023-03-15 | 30 | 5 | wave_eve |
| [php-src](php-src/target.yaml) | 50 | `e5b6f43ec781` | 2021-05-06 | 13 | 2 | wave_eve |
| [gpac](gpac/target.yaml) | 49 | `b890f1c443db` | 2024-01-17 | 42 | 5 | wave_eve |
| [assimp](assimp/target.yaml) | 42 | `d34cd103f477` | 2021-09-09 | 25 | 8 | measured_sweep |
| [libredwg](libredwg/target.yaml) | 39 | `d0accfd39bb1` | 2022-04-16 | 28 | 2 | wave_eve |
| [c-blosc2](c-blosc2/target.yaml) | 37 | `0e8bdfce66ba` | 2021-01-18 | 27 | 3 | wave_eve |
| [wolfssl](wolfssl/target.yaml) | 37 | `a13e9bde29c0` | 2021-01-18 | 18 | 2 | wave_eve |
| [serenity](serenity/target.yaml) | 36 | `84996c6567e0` | 2021-02-23 | 14 | 2 | wave_eve |
| [fluent-bit](fluent-bit/target.yaml) | 35 | `e5289e606c4b` | 2020-11-05 | 23 | 5 | wave_eve |
| [openthread](openthread/target.yaml) | 34 | `639b58eae762` | 2018-02-02 | 21 | 2 | wave_eve |
| [libavc](libavc/target.yaml) | 31 | `764ab7b70214` | 2023-02-15 | 10 | 4 | measured_sweep |
| [mruby](mruby/target.yaml) | 30 | `6b3b1012ca48` | 2021-10-12 | 15 | 2 | wave_eve |
| [libvips](libvips/target.yaml) | 29 | `257e01ecefa0` | 2021-05-17 | 10 | 2 | wave_eve |
| [matio](matio/target.yaml) | 29 | `b783c3e234ce` | 2021-01-25 | 7 | 2 | measured_sweep |
| [open62541](open62541/target.yaml) | 29 | `23131fe8aec1` | 2017-11-19 | 13 | 2 | wave_eve |
| [arrow](arrow/target.yaml) | 27 | `8b09ecc5c690` | 2020-01-16 | 23 | 2 | wave_eve |
| [libdwarf](libdwarf/target.yaml) | 26 | `2ee326bad2b4` | 2023-03-20 | 21 | 2 | wave_eve |
| [graphicsmagick](graphicsmagick/target.yaml) | 25 | `—` | — | 0 | 0 | unresolved |
| [radare2](radare2/target.yaml) | 25 | `ef5c59e0d443` | 2018-09-18 | 20 | 2 | wave_eve |
| [openh264](openh264/target.yaml) | 24 | `83a0eae9bbbd` | 2020-09-29 | 12 | 7 | measured_sweep |
| [libjxl](libjxl/target.yaml) | 23 | `35ad5de736b3` | 2021-10-27 | 13 | 2 | wave_eve |
| [sleuthkit](sleuthkit/target.yaml) | 23 | `5eabe4d554f0` | 2021-04-26 | 14 | 2 | wave_eve |
| [net-snmp](net-snmp/target.yaml) | 22 | `1e50b621f9e1` | 2021-10-20 | 9 | 2 | wave_eve |
| [curl](curl/target.yaml) | 21 | `ba67f7d65a42` | 2018-04-24 | 8 | 4 | wave_eve |
| [librawspeed](librawspeed/target.yaml) | 21 | `a17791452ef3` | 2017-09-24 | 17 | 3 | wave_eve |
| [PcapPlusPlus](PcapPlusPlus/target.yaml) | 20 | `65974d73c33a` | 2023-08-02 | 8 | 2 | measured_sweep |
| [mupdf](mupdf/target.yaml) | 20 | `867d6c72a346` | 2023-05-30 | 7 | 2 | wave_eve |
| [selinux](selinux/target.yaml) | 20 | `38a09b74024b` | 2021-01-04 | 14 | 2 | measured_sweep |
| [kimageformats](kimageformats/target.yaml) | 19 | `d734f2872745` | 2022-10-18 | 6 | 2 | wave_eve |
| [libarchive](libarchive/target.yaml) | 18 | `410ecbd3a7cb` | 2022-11-02 | 2 | 2 | measured_sweep |
| [lcms](lcms/target.yaml) | 17 | `3d3001f01189` | 2022-07-24 | 14 | 4 | wave_eve |
| [libheif](libheif/target.yaml) | 17 | `3dc3acbf739d` | 2025-05-05 | 2 | 2 | wave_eve |
| [hunspell](hunspell/target.yaml) | 16 | `6291cac8fb85` | 2022-09-12 | 8 | 3 | measured_sweep |
| [leptonica](leptonica/target.yaml) | 16 | `091ee190146b` | 2020-10-25 | 7 | 2 | wave_eve |
| [libraw](libraw/target.yaml) | 16 | `371161a06d7f` | 2021-07-27 | 9 | 2 | wave_eve |
| [pcre2](pcre2/target.yaml) | 16 | `69fee50e5fbc` | 2017-03-09 | 9 | 2 | wave_eve |
| [upx](upx/target.yaml) | 16 | `09c5e383223e` | 2024-01-09 | 9 | 5 | measured_sweep |
| [file](file/target.yaml) | 14 | `6382574724f9` | 2018-08-11 | 3 | 2 | measured_sweep |
| [freeradius-server](freeradius-server/target.yaml) | 14 | `10bc205ff66c` | 2021-10-06 | 9 | 3 | wave_eve |
| [hdf5](hdf5/target.yaml) | 14 | `bd7616cf98ae` | 2023-04-26 | 12 | 2 | measured_sweep |
| [icu](icu/target.yaml) | 14 | `667ee72b7c29` | 2023-08-21 | 10 | 1 | wave_eve |
| [htslib](htslib/target.yaml) | 13 | `23a67495c537` | 2021-01-25 | 5 | 4 | measured_sweep |
| [kamailio](kamailio/target.yaml) | 13 | `95fb987bd402` | 2024-10-11 | 6 | 2 | measured_sweep |
| [libxslt](libxslt/target.yaml) | 13 | `7238299d6484` | 2021-01-17 | 4 | 3 | measured_sweep |
| [openvswitch](openvswitch/target.yaml) | 13 | `f5129153e3b1` | 2018-07-10 | 12 | 2 | wave_eve |
| [pcl](pcl/target.yaml) | 13 | `09e914b0b3b1` | 2022-08-25 | 12 | 12 | measured_sweep |
| [rdkit](rdkit/target.yaml) | 13 | `b603d0d97ed4` | 2022-01-20 | 7 | 2 | wave_eve |
| [espeak-ng](espeak-ng/target.yaml) | 12 | `ccb1c31ba3cf` | 2021-11-07 | 11 | 3 | measured_sweep |
| [libhevc](libhevc/target.yaml) | 12 | `fbcad2ab1bd8` | 2019-10-03 | 6 | 3 | measured_sweep |
| [lwan](lwan/target.yaml) | 12 | `341dca6b2594` | 2019-04-29 | 9 | 2 | wave_eve |
| [openexr](openexr/target.yaml) | 12 | `379a2884afe9` | 2023-05-26 | 2 | 2 | measured_sweep |
| [samba](samba/target.yaml) | 12 | `d1277f4d0270` | 2020-02-07 | 3 | 2 | wave_eve |
| [aom](aom/target.yaml) | 11 | `5d8a6c3fd57f` | 2021-04-21 | 2 | 2 | measured_sweep |
| [ntopng](ntopng/target.yaml) | 11 | `47f248c8edbb` | 2023-05-22 | 5 | 2 | measured_sweep |
