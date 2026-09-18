# ScienceDB 提交卡片：upx

逐字段复制到 ScienceDB「提交数据」表单。文件在 `/tmp/memvul/release-upload/`
（先用 `python3 scripts/make_unit_tars.py --unit upx` 生成 tar）。

## 标题（中文）
MemVulBench v1.0.0 测试单元：upx（上游提交 09c5e383223e）

## 标题（英文）
MemVulBench v1.0.0 test unit: upx @ upstream commit 09c5e383223e

## 作者
芦笑瑜（Xiaoyu Lu）、魏强（Qiang Wei，通讯作者）、王云峰（Yunfeng Wang）；信息工程大学（Information Engineering University）

## 摘要 / 描述
MemVulBench 是面向 C/C++ 内存安全模糊测试的真实多漏洞基准（20 个测试单元、
292 个经核验的唯一漏洞指纹）。本数据集是其一个测试单元：上游仓库
https://github.com/upx/upx.git 在提交 09c5e383223e6f70222b8b04fffdb79919f9c40a 的未经修改源码上构建，
对外入口 prefix_mod_3（3 个路由），含 14 个经核验的唯一
漏洞指纹（expected 14 + 经审计额外
0），每个指纹有触发 PoC、最终入口首错日志与
SHA-256 清单。tar 内含最终聚合 Docker 镜像、14 个计分
PoC 与全部验证日志；按 run-config.json 回放，各 PoC 首错应与
logs/final-entry/ 下对应日志一致。软件与跨单元指纹索引见
https://github.com/explorerlxy/MemVulBench（标签 memvulbench-v1.0.0）。镜像内上游源码遵循其原始许可。

英文一句话版：One admitted test unit of MemVulBench v1.0.0 (20 units, 292
verified unique memory-vulnerability fingerprints in total): upstream
https://github.com/upx/upx.git at commit 09c5e383223e6f70222b8b04fffdb79919f9c40a, entry
prefix_mod_3 with 3 routes, 14 verified fingerprints with
PoCs, final-entry first-fault logs and SHA-256 manifests.

## 关键词
fuzzing; memory safety; benchmark; ARVO; OSS-Fuzz; C/C++; upx

## 许可
CC BY 4.0

## 版本
v1.0.0

## 关联论文
MemVulBench：面向 C/C++ 内存漏洞模糊测试的真实多漏洞基准构建（投稿中）。
软件仓库：https://github.com/explorerlxy/MemVulBench（标签 memvulbench-v1.0.0）

## 本记录文件清单（3 个）
- `upx-09c5e383223e-v1.0.0.tar`
- `manifest.json`
- `run-config.json`
