# Photo Analyzer

本地图片分析工具，分成两条独立路径：

- [local_gallery.html](/Users/Noah/Work/my_project/local_gallery.html)：直接双击打开即可用的轻量本地页面
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

- 本地图像描述模型：`Salesforce/blip-image-captioning-base`
- 视觉特征：亮度、对比度、饱和度、冷暖倾向、清晰度、宽高比
- 输出结果：基础信息、基础指标、caption、描述标签、中文总结
- 标签范围来自本地可编辑配置：`photo_analyzer/taxonomy.json`

若本地图像描述模型不可用，CLI 会自动退回纯规则标签，不会整次分析失败。

## 安装

```bash
python3 -m pip install -e .
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

生成 `results.json` 后，可直接打开 [local_gallery.html](/Users/Noah/Work/my_project/local_gallery.html) 并选择包含该文件的目录进行浏览。

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

Python 分析链路的最终标签严格限制在 [taxonomy.json](/Users/Noah/Work/my_project/photo_analyzer/taxonomy.json) 中。

这份配置按三组组织：

- `subject`：主体标签
- `scene`：场景标签
- `style`：风格/状态标签

每个标签项都包含：

- `id`
- `label`
- `group`
- `enabled`
- `trigger_terms`
- `metric_rules`
- `summary_priority`

后续新增标签时，只需要在 `taxonomy.json` 里追加新标签项；禁用标签时把 `enabled` 改成 `false` 即可。改完后运行测试验证：

```bash
python3 -m unittest discover -s tests -v
```

## 测试

```bash
python3 -m unittest discover -s tests -v
```
