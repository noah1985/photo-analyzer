# 本地 Hugging Face 权重（随仓库路径引用）

分析时**只从本目录加载**，不会在运行时联网下载。

## 一次性拉取（国内镜像）

在项目根目录执行：

```bash
python3 scripts/vend_hf_models.py
```

脚本默认使用 **`https://hf-mirror.com`**，将五个预设对应的模型快照写入本目录下各子文件夹。

若某次网络/SSL 中断，可只补下缺的预设，例如：

```bash
python3 scripts/vend_hf_models.py --only photo
python3 scripts/vend_hf_models.py --only git_large
```

指定其它镜像端点：

```bash
python3 scripts/vend_hf_models.py --endpoint https://hf-mirror.com
```

从 v1.2.1 起，若你本机仍留有旧的 **`microsoft_git-*-coco`** 目录，可删除后按上表重新 vend；当前预设已不再使用 GIT。

`git_large`（6.7B）等大仓库在下载过程中，部分分片可能经 Hugging Face 的存储中转域名拉取；若出现 SSL 中断，**重复执行** `vend_hf_models.py --only git_large` 即可续传。

## 目录与预设对应关系

| 预设 key | 子目录名 |
|----------|----------|
| `fast` | `Salesforce_blip-image-captioning-base` |
| `balanced` | `Salesforce_blip-image-captioning-large` |
| `detailed` | `nlpconnect_vit-gpt2-image-captioning` |
| `photo` | `Salesforce_blip2-opt-2.7b` |
| `git_large` | `Salesforce_blip2-opt-6.7b` |

## 覆盖路径（测试或自定义）

设置环境变量 **`PHOTO_ANALYZER_HF_VENDOR_ROOT`** 指向包含上述子目录的文件夹，可替代默认的 `models/hf`。
