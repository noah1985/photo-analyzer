# 技术说明

## 架构概览

项目分两条主线：

- **Python 分析核心**（`photo_analyzer/`）
- **Swift 本地桌面 App**（`PhotoAnalyzerApp/`）

Swift App 不直接做模型推理，调用 Python CLI 的 `--stream` 模式，通过 JSONL 事件（`start` → `model_loading` → `model_ready` → `progress` → `result` → `done`）实时交互。

### 分析流程（三层架构）

```
图片
  ↓
Layer 1 – Signals：读图 → 提取视觉指标（亮度/对比度/饱和度/冷暖/清晰度/宽高比）→ 调用本地 caption 模型 → 输出 Signals 对象
  ↓
Layer 2 – Scoring：遍历 taxonomy.json 中每个标签的 rules（token_any / phrase_any / metric_lt / metric_gt / metric_eq），累加命中分值
  ↓
Layer 3 – Selection：按分值降序、组内 max_tags 上限、conflicts 互斥 → 选出最终标签
  ↓
后处理 Refinements：少量 Python 启发式（食物 vs 人像消歧、figurine 排除动物等）
  ↓
输出：4 组受控标签 + 中文总结
```

### 关键文件

| 文件 | 职责 |
|------|------|
| `photo_analyzer/core.py` | 三层管线（`extract_signals` → `score_all_tags` → `select_tags`），后处理 refinements，中文总结 |
| `photo_analyzer/captioning.py` | 模型预设定义、本地缓存命中、caption 生成 |
| `photo_analyzer/cli.py` | 命令行入口、目录分析、流式 JSONL、HTML 画廊导出 |
| `photo_analyzer/taxonomy.json` | 声明式标签配置（v2）：groups / tags / rules / conflicts |
| `PhotoAnalyzerApp/Sources/` | Swift UI、AnalyzerService（解析 JSONL）、AppState、Models |

### Swift ↔ Python 输出契约

每张图的 JSON 输出含：`caption`、`caption_model`、`caption_model_label`、`model_initialization_seconds`、`analysis_duration_seconds`、`tag_groups`（主结构）、`tags`（扁平汇总）、`summary`。

---

## 模型

项目支持 5 个预设，定义在 `captioning.py`：

| key | HF repo | 定位 |
| --- | --- | --- |
| `fast` | `Salesforce/blip-image-captioning-base` | 快速初筛 |
| `balanced` | `Salesforce/blip-image-captioning-large` | **默认主力** |
| `detailed` | `nlpconnect/vit-gpt2-image-captioning` | 自由描述更开放 |
| `photo` | `Salesforce/blip2-opt-2.7b` | BLIP-2，高质量补充 |
| `git_large` | `Salesforce/blip2-opt-6.7b` | BLIP-2 更大解码器，能力上限最高，CPU 下很慢 |

推荐顺序：`balanced` → `photo` → `git_large` → `fast` → `detailed`。

运行时只从 `models/hf/` 加载，不联网下载。首次拉取：`python3 scripts/vend_hf_models.py`（详见 `models/hf/README.md`）。

### 已放弃的方案

- `microsoft/git-base-coco` / `microsoft/git-large-coco`：易出现物体混淆，已替换为 BLIP-2
- `SmolVLM` 系列（2.2B / 500M / 256M）：结构化输出不稳定，依赖链重

结论：小体量 VLM 在本项目的摄影标签任务上不可靠，当前路线收敛为传统 caption + taxonomy 映射。

---

## 评测

`scripts/run_eval_five_rounds_random.py` 提供多轮随机抽样评测：

```bash
PYTHONPATH=. python3 scripts/run_eval_five_rounds_random.py --rounds 10 --model fast
```

- 图集目录：默认 `/Users/Noah/Pictures/分享输出`，可用 `--root` 或 `PHOTO_ANALYZER_IMAGE_ROOT` 覆盖
- 可选参数：`--rounds`、`--per-round`、`--model`、`--base-seed`、`--out`
- 产出在 `var/eval_runs/`（已 `.gitignore`）

详细参数说明：`python3 scripts/run_eval_five_rounds_random.py --help`
