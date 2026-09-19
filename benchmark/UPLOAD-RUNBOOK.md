# MemVulBench v1.0.0 上传手册（仅 Hugging Face）

状态：**已执行完毕（2026-09-19）**。数据集公开地址：
https://huggingface.co/datasets/Fisho0/MemVulBench（66 文件 = 20 单元×3 + 索引）。
本手册保留作再发布/增量发布的操作参考。

## 流程（如需重做或新增单元）

```bash
hf auth login                          # write 权限 token
python3 scripts/hf_upload.py --create  # 建私有仓库 + 主页卡片/索引
python3 scripts/hf_upload.py --unit <project>   # 逐单元:打 tar→上传→清理(断点重跑即续传)
python3 scripts/hf_upload.py --public   # 抽查无误后转公开
```

注意事项：

- `/tmp` 空间有限：逐单元串行，脚本自动生成并删除 tar（峰值约 6.1 GB）。
- 上传走本机代理时，代理变量必须用 http:// scheme（`socks://` 会被 httpx 拒绝）。
- 国内匿名下载验证：`HF_ENDPOINT=https://hf-mirror.com huggingface-cli download ...`
- 传输中主机睡眠会导致进度停滞，恢复后重跑同一条命令即可续传。
