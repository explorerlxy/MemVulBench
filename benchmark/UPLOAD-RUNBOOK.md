# MemVulBench v1.0.0 上传执行手册（Hugging Face 为主）

状态：**软件层已完成**（GitHub `explorerlxy/MemVulBench`，标签
`memvulbench-v1.0.0`）。数据层改为 **Hugging Face 数据集仓库**：零审核、
发布即时、公开数据集免费（单文件上限约 50 GB，最大单元 tar 6.1 GB）、
国内读者经 <https://hf-mirror.com> 免代理免账号下载。
DOI 需要时再补 Zenodo 镜像（附 D）；ScienceDB 卡片保留备用（附 E）。

## A. 软件层（已完成 ✅）

<https://github.com/explorerlxy/MemVulBench>，标签 `memvulbench-v1.0.0`。

## B. Hugging Face（主通道）

**一次性准备**

```bash
# 1. HF 账号 -> Settings -> Access Tokens -> New token（write 权限）
# 2. 登录（huggingface_hub 已装到用户目录，hf 在 ~/.local/bin）
hf auth login
# 3. 建私有数据集仓库并上传主页卡片/指纹索引/manifest/核查文件
python3 scripts/hf_upload.py --create
```

**逐单元上传（tar 自动生成→上传→清理；断点可续，重跑即续传）**

```bash
python3 scripts/hf_upload.py --unit arrow
# ……对 20 个单元依次执行：
for p in arrow assimp espeak-ng fluent-bit ghostpdl gpac hdf5 libavc libdwarf \
         libraw libxml2 ndpi openh264 opensc openvswitch PcapPlusPlus pcl \
         selinux sleuthkit upx; do
    python3 scripts/hf_upload.py --unit $p
done
```

`/tmp` 仅 26 GB 空闲：脚本逐单元生成并删除 tar（峰值 6.1 GB），勿同时
手工生成多个 tar。

**发布**

```bash
# 全部传完、在网页上抽查文件树无误后：
python3 scripts/hf_upload.py --public
```

主页卡片 `benchmark/HF-CARD.md` 已写好（含国内 hf-mirror 下载说明与引用
BibTeX）。

**匿名验证**（发布后）：

```bash
HF_ENDPOINT=https://hf-mirror.com huggingface-cli download \
    explorerlxy/MemVulBench --repo-type dataset \
    --include "units/arrow/*" --local-dir /tmp/hf-check
```

## C. 回填（发布后）

1. 仓库根 `README.md` 与 `papers/MemVulBench/manuscript.md` 数据可用性声明
   写入数据集地址 `https://huggingface.co/datasets/explorerlxy/MemVulBench`
   （及 hf-mirror 提示）；HF 卡片的 Citation 指回 GitHub 与论文。
2. `git add <涉及文件> && git commit -m "回填 v1.0.0 数据集地址" && git push`。
   **不要移动 `memvulbench-v1.0.0` 标签**。

## 附 D：Zenodo（可选，补 DOI 用）

```bash
export HTTPS_PROXY=http://127.0.0.1:17891     # 走本机 Clash
export ZENODO_TOKEN=<token>
python3 scripts/zenodo_upload.py --unit <p>   # 21 条同布局；秒发无审核
```

## 附 E：ScienceDB（可选，国内期刊生态）

卡片在 `benchmark/checks/sciencedb-metadata/`；需人工审核（约 1–3 个
工作日），投稿目标明确后再做不迟。
