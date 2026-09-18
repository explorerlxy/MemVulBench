# MemVulBench v1.0.0 上传执行手册

共 22 条归档记录：**1 个软件仓库（GitHub）+ 20 个单元记录 + 1 个索引记录（Zenodo）**。
每条 Zenodo 记录 3 个文件（1 个单元 tar + manifest.json + run-config.json），
远低于单记录 50 GB / 100 文件上限。

## A. 软件层：GitHub（约 10 MB，先做）

```bash
# 1. 在 GitHub 网页上新建空仓库 MemVulBench（不要初始化 README）
# 2. 本仓库根目录：
git remote add origin git@github.com:<你的用户名>/MemVulBench.git
git push -u origin master --tags        # 推送 master 与 memvulbench-v1.0.0
# 3. （可选）在 tag memvulbench-v1.0.0 上建 GitHub Release，
#    附件挂 benchmark/fingerprint-index.json（<2 MiB，远低于 2 GiB 资产上限）
```

> GitHub Release 不放镜像（单文件 <2 GiB 限制）；镜像走 Zenodo。

## B. 单元层：Zenodo（20 条，按单元逐个执行）

准备：Zenodo 账号 → Profile → Applications → Personal access token
（勾选 `deposit:actions` 与 `deposit:write`），然后：

```bash
export ZENODO_TOKEN=<你的token>

# 强烈建议先在沙箱空跑一条，熟悉流程（不产生正式 DOI，可随便删）：
python3 scripts/zenodo_upload.py --unit libxml2 --sandbox

# 正式上传（每条命令：打 tar → 传镜像 → 传 manifest/run-config → 生成草稿）：
for p in arrow assimp espeak-ng fluent-bit ghostpdl gpac hdf5 libavc libdwarf \
         libraw libxml2 ndpi openh264 opensc openvswitch PcapPlusPlus pcl \
         selinux sleuthkit upx; do
    python3 scripts/zenodo_upload.py --unit $p
done
```

每条完成后到 `https://zenodo.org/deposit/<id>` 检查页面（文件齐全、
描述里的提交号正确），确认无误后在网页上点 **Publish**（或
`python3 scripts/zenodo_upload.py --unit <p> --deposit-id <id> --publish`）。

注意：

- 逐单元串行做；tar 临时占 `/tmp/memvul/release-upload/`（最大单元
  6.1 GB），上传校验通过后可 `rm /tmp/memvul/release-upload/*.tar` 回收。
- 全量 66.56 GB，上传耗时取决于家宽上行（如 30 Mbps ≈ 每吉比特 5 分钟，
  全量约 5–6 小时；Zenodo 断点可续：`--deposit-id` 恢复同一草稿重传）。
- 脚本自动把每个 deposit id 记到 `benchmark/checks/zenodo-dois.json`。

## C. 索引记录：第 21 条

```bash
python3 scripts/zenodo_upload.py --index
```

上传 `fingerprint-index.json` + `manifest.json` + README，让只看 Zenodo 的
读者也能按指纹定位到各单元记录。

## D. 回填（发布完成后）

1. 把各正式 DOI 填进 `benchmark/manifest.json`（加 `unit_dois` 字段）与
   `benchmark/checks/zenodo-dois.json` 的 `published: true`。
2. 仓库根 `README.md` 和 `papers/MemVulBench/manuscript.md` 的数据与代码
   可用性声明：把"尚未确认公开下载地址"替换为 GitHub 地址 + 各 DOI；
   Zenodo 记录描述里回填 GitHub 链接（脚本已写入 tag 号，补仓库 URL 即可）。
3. `git add -A && git commit -m "回填 v1.0.0 公开地址与 DOI"` 并推送。
   **不要移动 memvulbench-v1.0.0 标签**——回填进 master 即可，标签保持
   指向冻结内容。
