# v1.2.0 — GIT Large（小于 5 亿参数）试验预设

## 模型

- 新增预设 **`git_large`** → `microsoft/git-large-coco`（约 4 亿参数，在 5 亿参数预算内）。
- 仍使用现有 **`pipeline("image-to-text")`** 路径，与 SmolVLM 等指令式小 VLM 不同，避免模板化输出问题。
- CLI `--model`、Swift 模型选择器已包含该选项。

## 版本号

- `ANALYSIS_VERSION` / `pyproject.toml` / App `bundledUIVersion` / 打包 `Info.plist` → **1.2.0**。

## 文档

- `README.md`、`technical_notes/MODELS.md` 已更新。

验证：`python3 -m unittest discover -s tests -v`
