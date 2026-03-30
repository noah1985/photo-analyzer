# 项目文档索引

根目录 [README.md](../README.md) 为使用说明与安装入口；本页汇总其余文档位置。

## 运维与发布

| 文档 | 说明 |
|------|------|
| [RESTART_REQUIREMENTS.md](RESTART_REQUIREMENTS.md) | 重启 / 环境相关注意 |
| [release-notes/v1.2.0-git-large/CHANGES.md](release-notes/v1.2.0-git-large/CHANGES.md) | v1.2.0 变更（git_large 等） |
| [release-notes/v1.1.0-ui-model-update/CHANGES.md](release-notes/v1.1.0-ui-model-update/CHANGES.md) | v1.1.0 变更（UI / 模型） |

## 技术说明（`technical_notes/`）

| 文档 | 说明 |
|------|------|
| [technical_notes/README.md](../technical_notes/README.md) | 技术笔记总览与结论摘要 |
| [MODELS.md](../technical_notes/MODELS.md) | 可选 caption 模型与推荐 |
| [ARCHITECTURE.md](../technical_notes/ARCHITECTURE.md) | CLI / App / taxonomy 结构 |
| [ISSUES.md](../technical_notes/ISSUES.md) | 已知问题与处理记录 |
| [EVAL_MULTI_ROUND_GIT_LARGE.md](../technical_notes/EVAL_MULTI_ROUND_GIT_LARGE.md) | 多轮评测与校正流程（含随机抽样脚本） |

## 本地生成物（勿提交）

| 路径 | 说明 |
|------|------|
| `var/eval_runs/` | `scripts/run_eval_five_rounds_random.py` 默认输出；已 `.gitignore` |
| `PhotoAnalyzerApp/.build/`、`PhotoAnalyzer.app/` | Swift 本地构建产物 |
| `models/hf/*` | Hugging Face 权重（见 `models/hf/README.md`） |
