# Photo Analyzer

本地图片分析工具，分成两条独立路径：

- [local_gallery.html](local_gallery.html)：直接双击打开即可用的轻量本地页面
- Python CLI：本地模型优先的图片分析入口，负责更强的离线分析能力

## HTML 路径

`local_gallery.html` 保持轻量前端规则分析：

- 可以直接双击打开
- 通过浏览器本地目录选择 API 读取 Python 产出的 `results.json`
- 只按你输入的数量随机展示结果，最大 100 张
- 展示图片缩略图、中文标签和中文总结
- 不依赖模型下载、CDN 或 web service

## Python 路径

Python 侧采用“本地图像描述模型 + 轻量视觉特征”的组合：

- 本地图像描述模型：基于 Hugging Face 的本地 caption 模型
- 当前默认主力模型：`Salesforce/blip-image-captioning-large`
- 当前高质量补充模型：`Salesforce/blip2-opt-2.7b`（预设 `photo`），更强一档：`Salesforce/blip2-opt-6.7b`（预设 `git_large`）
- 视觉特征：亮度、对比度、饱和度、冷暖倾向、清晰度、宽高比
- 输出结果：基础信息、基础指标、caption、4 组受控标签、中文总结
- 标签范围来自本地可编辑配置：`photo_analyzer/taxonomy.json`

模型预设：

- `fast`：`Salesforce/blip-image-captioning-base`，适合快速初筛
- `balanced`：`Salesforce/blip-image-captioning-large`，当前默认主力
- `detailed`：`nlpconnect/vit-gpt2-image-captioning`，自由描述更开放
- `photo`：`Salesforce/blip2-opt-2.7b`（BLIP-2），比传统 BLIP 更强，作高质量补充；默认仍推荐 `balanced`
- `git_large`：`Salesforce/blip2-opt-6.7b`（BLIP-2 更大解码器），强于 `photo` 但更慢、下载与内存更大；默认仍推荐 `balanced`

说明：

- 早期尝试过 `SmolVLM` 等小型多模态指令模型，但当前已经停止作为主实现
- 当前主链路已经收敛为：`caption -> taxonomy 映射 -> 4 组标签 -> 中文总结`
- 技术说明（架构、模型、评测）：[technical_notes/README.md](technical_notes/README.md)

若本地图像描述模型不可用，CLI 会自动退回纯规则标签，不会整次分析失败。

**模型文件**：运行时**只从项目内 `models/hf/` 加载**，不会自动联网下载。请在本机执行一次（默认走国内镜像 **hf-mirror.com**）：

```bash
python3 scripts/vend_hf_models.py
```

也可先设置 `export HF_ENDPOINT=https://hf-mirror.com` 再运行脚本。自定义权重根目录见 `models/hf/README.md`（`PHOTO_ANALYZER_HF_VENDOR_ROOT`）。

## 安装

```bash
python3 -m pip install -e .
python3 scripts/vend_hf_models.py
```

## 使用

分析单张图片或整个目录：

```bash
photo-analyzer analyze /path/to/image.jpg
photo-analyzer analyze /path/to/photo-folder
```

随机抽样并导出静态 HTML + JSON：

```bash
photo-analyzer sample-gallery /path/to/photo-folder --count 100 --seed 20260421
```

生成 `results.json` 后，可直接打开 [local_gallery.html](local_gallery.html) 并选择包含该文件的目录进行浏览。

本地桌面入口仍保留：

```bash
photo-analyzer app
```

未安装入口脚本时：

```bash
python3 -m photo_analyzer analyze /path/to/image.jpg
```

## 输出内容

- HTML 版：图片缩略图 + 描述性标签
- CLI 版：文件信息 + 基础指标 + caption + 标签 + 中文总结

## 标签配置

Python 分析链路的最终标签严格限制在 [photo_analyzer/taxonomy.json](photo_analyzer/taxonomy.json) 中。

这份配置按四组组织（**仅**下列中文 `label`，勿在 taxonomy 中增加未列出项）：

- `subject_content`（题材 / 内容）：人像、建筑、风光、食物、动物、运动
- `composition_distance`（构图 / 景别）：特写、近景、宽景、对称、主体突出、**微距**（可与题材「动物」等同时出现；每组仍最多 2 个标签）
- `scene_lighting`（场景 / 光线）：室内、室外、夜景、日落、低光、逆光
- `style_impression`（色调倾向）：暖色调、冷色调、黑白、高对比、低对比、高饱和、低饱和、明亮

每组最多输出 2 个标签，允许为空。

`taxonomy.json` 为 **version 2**：顶层含 `groups`（每组中文标题与 `max_tags`）与 `tags` 列表。每个标签含 `id`、`label`、`group`、`enabled`、**`rules`**（如 `token_any`、`phrase_any`、`metric_lt` / `metric_gt` / `metric_eq` 及 `score`）、**`conflicts`**（与同组其它标签互斥时填写对方中文 `label`）。

若需调整识别规则，在既有 `label` 上改 `rules` 或 `enabled`；**不要**增加上表以外的 `label`。改完后运行测试验证：

```bash
python3 -m unittest discover -s tests -v
```

## 测试

```bash
python3 -m unittest discover -s tests -v
```
