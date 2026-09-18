# MemVulBench v1.0.0 上传执行手册（ScienceDB 为主）

状态：**软件层已完成**——GitHub `explorerlxy/MemVulBench`（master + 标签
`memvulbench-v1.0.0` 已推送）。剩余：ScienceDB 21 条记录 + DOI 回填。
Zenodo 作为可选国际镜像，流程附在末尾。

## A. 软件层（已完成 ✅）

- 仓库：<https://github.com/explorerlxy/MemVulBench>
- 冻结标签：`memvulbench-v1.0.0`
- 可选补充：在该标签上建 GitHub Release，附件挂
  `benchmark/fingerprint-index.json`；国内访问可再推一份 Gitee 镜像
  （仓库 ~10 MB，低于 500 MB 限制；开源仓库需实名审核 1–2 天；
  Release 附件限 100 MB，不放镜像）。

## B. ScienceDB：21 条记录（20 单元 + 1 索引）

**一次性准备**

1. 注册/登录 <https://www.scidb.cn>（sciencedb.cn，中科院通行证可登）。
2. 先传一个最小单元（如 libxml2）试探单文件上限；帮助中心确认 GB 级
   单文件可直传。若有上限：改分卷压缩，或把 logs/ 与 image 拆成两条记录。
3. 生成全部 21 张提交卡片（标题/摘要/关键词/许可逐字段可复制）：

```bash
python3 scripts/make_unit_tars.py --cards
ls benchmark/checks/sciencedb-metadata/   # 20 张单元卡 + _index.md
```

**逐单元执行**（一条记录约 10 分钟操作 + 上传时间）：

```bash
# 1. 生成该单元的 tar（放 /tmp/memvul/release-upload/，最大 6.1 GB）
python3 scripts/make_unit_tars.py --unit ghostpdl

# 2. 网页操作：提交数据 → 按卡片 benchmark/checks/sciencedb-metadata/ghostpdl.md
#    逐字段粘贴（标题/作者/摘要/关键词 CC BY 4.0 / 版本 v1.0.0），
#    上传 3 个文件：tar + benchmark/units/ghostpdl/manifest.json + run-config.json
#    → 提交审核 → 通过后发布，记下 DOI/CSTR

# 3. 删除本地 tar，释放空间
python3 scripts/make_unit_tars.py --clean ghostpdl
```

20 个单元依次：arrow assimp espeak-ng fluent-bit ghostpdl gpac hdf5 libavc
libdwarf libraw libxml2 ndpi openh264 opensc openvswitch PcapPlusPlus pcl
selinux sleuthkit upx。最后传**索引记录**（卡片 `_index.md`，文件为
`benchmark/fingerprint-index.json` + `manifest.json` + `README.md`）。

**登记 DOI**：每条发布后在 `benchmark/checks/zenodo-dois.json` 同级新建
`benchmark/checks/sciencedb-dois.json`，格式：

```json
{ "<记录标识>": {"record": "ghostpdl", "doi": "10.11922/…", "cstr": "…"} }
```

## C. 回填（全部发布后）

1. `benchmark/manifest.json` 增加 `unit_dois` 字段；仓库根 `README.md` 与
   `papers/MemVulBench/manuscript.md` 数据可用性声明写入 ScienceDB DOI
   （投国际 venue 可并列 Zenodo 镜像 DOI）。
2. ScienceDB 各记录描述里已含 GitHub 链接，无需回改。
3. `git add <涉及文件> && git commit -m "回填 v1.0.0 ScienceDB DOI"` 并
   `git push`。**不要移动 `memvulbench-v1.0.0` 标签**——回填进 master。

## 附：Zenodo 可选镜像

```bash
export ZENODO_TOKEN=<token>
python3 scripts/zenodo_upload.py --unit libxml2 --sandbox   # 演练
python3 scripts/zenodo_upload.py --unit <p>                 # 正式（支持 --deposit-id 续传）
python3 scripts/zenodo_upload.py --index
```

软件仓库地址已在脚本元数据中指向 `explorerlxy/MemVulBench`。
