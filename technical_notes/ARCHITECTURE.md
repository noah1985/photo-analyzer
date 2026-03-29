# Architecture

## Overview

当前项目分成两条主线：

- Python 分析核心
- Swift 本地桌面 App

另外保留一个轻量 HTML 页面，但当前主要产品路径已经是 Swift App + Python CLI。

## Python Side

核心目录：

- [photo_analyzer](../photo_analyzer)

关键文件：

- [captioning.py](../photo_analyzer/captioning.py)
  - 模型预设定义
  - 本地缓存命中与下载
  - caption 生成
- [core.py](../photo_analyzer/core.py)
  - 图片读取
  - 基础视觉指标提取
  - taxonomy 映射
  - 4 组标签整理
  - 中文总结生成
- [cli.py](../photo_analyzer/cli.py)
  - 命令行入口
  - 目录分析
  - 流式 JSON 输出
  - HTML 画廊导出
- [taxonomy.json](../photo_analyzer/taxonomy.json)
  - 受控标签集合
  - 分为 4 个固定分组

## Python Analysis Flow

主流程：

1. 读取图片
2. 提取基础指标
   - 亮度
   - 对比度
   - 饱和度
   - 冷暖倾向
   - 清晰度
3. 调用本地图像描述模型生成 caption
4. 将 caption 映射到 taxonomy
5. 输出 4 组标签：
   - `subject_content`
   - `scene_lighting`
   - `composition_distance`
   - `style_impression`
6. 生成中文总结

## Swift App Side

核心目录：

- [PhotoAnalyzerApp](../PhotoAnalyzerApp)

关键文件：

- [AnalyzerService.swift](../PhotoAnalyzerApp/Sources/AnalyzerService.swift)
  - 调用 Python CLI
  - 解析 JSONL 流事件
- [AppState.swift](../PhotoAnalyzerApp/Sources/AppState.swift)
  - 管理目录选择、状态、进度、结果和错误
- [ContentView.swift](../PhotoAnalyzerApp/Sources/ContentView.swift)
  - UI 展示
  - 模型选择
  - 进度条
  - 卡片布局
- [Models.swift](../PhotoAnalyzerApp/Sources/Models.swift)
  - Swift 端的数据结构

## Swift <-> Python Contract

Swift App 不直接做模型推理，而是调用：

- `photo-analyzer analyze-dir ... --stream`

Python 通过 JSONL 输出这些事件：

- `start`
- `model_loading`
- `model_download_progress`
- `model_ready`
- `progress`
- `result`
- `error`
- `done`

以上列表与当前 [cli.py](../photo_analyzer/cli.py) 中 `_emit(...)` 的实现保持一致；后续如果流式事件有增删，应该先改代码，再同步这里的文档。

Swift 负责：

- 实时展示下载进度
- 展示模型初始化耗时
- 展示每张图片单独分析耗时
- 展示 4 组标签和中文总结

## Current Output Contract

每张图的核心输出包含：

- `caption`
- `caption_model`
- `caption_model_label`
- `model_initialization_seconds`
- `analysis_duration_seconds`
- `tag_groups`
- `tags`
- `summary`

其中：

- `tag_groups` 是主结构
- `tags` 是扁平汇总字段

## Current Design Principle

当前架构已经明确收敛到：

- 模型只负责提供 caption
- taxonomy 决定最终标签语言
- Swift 只负责展示，不承担分析逻辑
- 复杂的结构化多模态实验不再作为主架构的一部分
