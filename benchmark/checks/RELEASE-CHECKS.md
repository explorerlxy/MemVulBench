# 发布前核查记录（2026-09-18）

依据 `papers/MemVulBench/release-plan.md` 第 3 节执行。各项结果如下；
标注 **pending** 的项目不阻塞打包，但正式对外上传前必须闭环。

## 1. 哈希核对

- **最终镜像**：20/20 单元聚合镜像 tar 全量重算 SHA-256，与
  `aggregation.image_archive_sha256` 记录全部一致（`hash-verification.json`）。
- **二进制与包装器**：各单元 `manifest.json` 记录的最终二进制、包装器源
  SHA-256 取自审定记录；arrow 单元于 2026-09-18 在加载容器内实测核对一致。
- **PoC 与日志**：`build_release.py` 生成清单时对 301 个计分 PoC、301 条
  最终入口日志、880 条验证日志逐文件计算 SHA-256 并写入单元清单。
- **指纹账本**：`fingerprint-index.json` 292 指纹与准入决定逐单元计数一致。

## 2. 路径与敏感信息（`path-scan.json`，扫描 1701 个文件）

- 凭据 / 私钥：**0 命中**。
- 本机绝对路径：125 处，全部位于历史记录的 provenance 字段与代码默认值。
  处置：代码默认路径已改为环境变量可覆盖（`MEMVUL_ARVO_DB`、
  `MEMVUL_POC_STORE`、`MEMVUL_CACHE_ROOT`、`MEMVUL_IMAGE_STORE`）；
  发布索引一律使用单元相对路径，不以主机路径作公开定位。
- `/tmp/memvul` 定位：19 处，均为操作约定文档或记录性字段；指纹索引已
  重映射到 `units/<p>/logs/final-entry/`。
- Email：手稿中为作者通讯信息（有意公开）；另 2 处为 arrow 两个 PoC 的
  二进制字节误报。
- 已删除 LibreOffice 残留锁文件 `papers/MemVulBench/.~lock.*`。

## 3. 许可与再分发（操作员 2026-09-18 决定：从简）

- 已落地：仓库根 `LICENSE`（MIT，原创代码）、`DATA-LICENSE`（CC BY 4.0，
  数据与文档）。
- 逐单元上游许可核对按操作员决定跳过；镜像内上游源码遵循其原始许可。
  PoC 输入出自 OSS-Fuzz / ARVO 公开问题记录，出处已在索引中逐条关联。
- 安全披露：本版全部漏洞为已公开修复的历史问题（目录 `fix_commit` 均为
  上游已合入修复），无新漏洞披露义务。

## 4. 匿名读者可达性

索引 → 单元清单 → 运行配置 → 日志的引用链已程序化验证：292 指纹的
`final_entry_logs` 与见证 PoC 引用零缺失。镜像加载、编译与 PoC 回放的
实物验收属操作员职责（arrow 已于 2026-09-18 逐条执行并记录），不在
打包自动化范围内。

## 5. 版本冻结

- git 提交与标签 `memvulbench-v1.0.0`（本地；仓库尚无远程，推送地址待定）。
- 软件层（GitHub tag memvulbench-v1.0.0）与数据层（Hugging Face 数据集
  Fisho0/MemVulBench，2026-09-19 公开）已发布并回填论文可用性声明。
  DOI 类持久标识通道（Zenodo）按操作员决定裁撤，仅保留 HF。
