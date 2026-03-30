# 多轮实测 + 逐轮校正：固定样本 × `git_large`

本文描述一种 **可复现** 的标签质量评估流程：从图集中 **固定抽取少量照片**，用 **最大 caption 模型 `git_large`**（BLIP-2 OPT 6.7B）跑 **多轮推理**；**每一轮结束后**根据输出做 **小范围逻辑校正**（主要改 `photo_analyzer/core.py`、必要时 `taxonomy.json`），补 **回归单测**，再进入下一轮。适合交给后续 agent 按相同节奏接手。

---

## 1. 目标与适用场景

| 目标 | 说明 |
|------|------|
| 发现真实 caption 下的误判 | 小样本 + 大模型更容易暴露「题材漏标、互斥标签并存、泛化标签抢 slot」等问题 |
| 控制变量 | **同一批文件路径** + **同一 `model_key`**，便于对比「改代码前后」差异 |
| 迭代方式 | **测 → 记问题 → 改一小点 → 单测 → 再测**，避免一次大改难以归因 |

不适用：全量图库压测、性能基准（本流程偏重 **标签语义质量**）。

---

## 2. 前置条件

### 2.1 环境与模型

- 工作目录：项目根目录（含 `photo_analyzer/`）。
- `PYTHONPATH=.`（或已 `pip install -e .`）。
- 本机已 vend 好 `git_large` 对应权重目录（见 `photo_analyzer/captioning.py` 里 `VENDOR_DIR_NAMES["git_large"]`，默认在 `models/hf/Salesforce_blip2-opt-6.7b`；亦可通过环境变量 `PHOTO_ANALYZER_HF_VENDOR_ROOT` 指向快照根目录）。
- **CPU 可跑但很慢**；首轮会加载分片 checkpoint，耗时明显增加。
- 分析入口：`photo_analyzer.core.analyze_image(path, model_key="git_large")`。

### 2.2 图集路径（可按任务替换）

此前实践使用用户图集目录（示例）：

```text
/Users/Noah/Pictures/分享输出
```

接手时请 **确认目录存在且可读**；若路径不同，只需改下文脚本里的 `root` 变量。

### 2.3 版本号策略（与产品约定对齐）

若仓库约定 **App / `ANALYSIS_VERSION` / `pyproject.toml` 不因单次评测小改而 bump**，则校正逻辑时 **不要顺带改版本号**；仅当用户明确要求发版时再统一升版本。

---

## 3. 固定 5 张图：生成清单（manifest）

**原则**：用 **固定随机种子** 从目录中抽取固定数量（如 5 张），把 **绝对路径列表** 写入 JSON，后续每一轮都读同一文件，保证可复现。

示例（项目根目录执行）：

```python
import json
import random
from pathlib import Path

root = Path("/Users/Noah/Pictures/分享输出")  # 按实际环境修改
exts = {".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG"}
files = sorted(
    p for p in root.iterdir()
    if p.is_file() and p.suffix in exts and not p.name.startswith(".")
)
random.seed(12345)  # 固定种子；换种子即换一套「固定样本」
manifest = [str(p.resolve()) for p in random.sample(files, min(5, len(files)))]
Path("tmp_five_manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print("manifest:", *[Path(p).name for p in manifest], sep="\n  ")
```

**产出**：`tmp_five_manifest.json`（工作区根目录，可提交到临时分支或留在本机；**不要**把用户隐私路径提交到公开仓库）。

**接手 agent 建议**：若 manifest 已存在且任务要求「同一批对比」，**优先复用**现有 `tmp_five_manifest.json`，不要随意换种子，除非用户要求换一批图。

---

## 4. 单轮评测：跑模型并落盘

### 4.1 每轮输出文件命名

约定（可按项目习惯微调，但需前后一致）：

| 文件 | 含义 |
|------|------|
| `tmp_round_<N>_git_large.json` | 第 N 轮结构化结果 |

JSON 建议结构（便于 diff 与脚本解析）：

```json
{
  "elapsed_s": 42.5,
  "rows": [
    {
      "path": "/abs/path/to/file.jpg",
      "caption": "...",
      "tag_groups": { "subject_content": [], "scene_lighting": [], ... },
      "tags": []
    }
  ]
}
```

### 4.2 单轮脚本示例（每轮新进程，会重复加载大模型）

```python
import json
import time
from pathlib import Path
from photo_analyzer.core import analyze_image

paths = json.loads(Path("tmp_five_manifest.json").read_text(encoding="utf-8"))
round_n = 1  # 每轮改这里
rows = []
t0 = time.perf_counter()
for p in paths:
    print(Path(p).name, "...", flush=True)
    r = analyze_image(p, model_key="git_large")
    rows.append({
        "path": p,
        "caption": r.caption,
        "tag_groups": r.tag_groups,
        "tags": r.tags,
        "errors": r.errors,
    })
elapsed = time.perf_counter() - t0
Path(f"tmp_round_{round_n}_git_large.json").write_text(
    json.dumps({"elapsed_s": round(elapsed, 2), "rows": rows}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
```

### 4.3 多轮在同一 Python 进程内连跑（省掉重复加载，仅用于「验证稳定」）

在 **同一校正版本** 下连跑 `round_n = 3,4,5` 时，可在一个进程里循环调用 `analyze_image`，**只加载一次** `git_large`，显著省时间。注意：**若中间改过代码，应重启进程**再跑下一轮，避免旧模块残留。

```python
import json
import time
from pathlib import Path
from photo_analyzer.core import analyze_image

paths = json.loads(Path("tmp_five_manifest.json").read_text(encoding="utf-8"))
for round_n in (3, 4, 5):
    rows = []
    t0 = time.perf_counter()
    for p in paths:
        r = analyze_image(p, model_key="git_large")
        rows.append({"path": p, "caption": r.caption, "tag_groups": r.tag_groups})
    elapsed = time.perf_counter() - t0
    Path(f"tmp_round_{round_n}_git_large.json").write_text(
        json.dumps({"elapsed_s": round(elapsed, 2), "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"round {round_n} {elapsed:.1f}s")
```

---

## 5. 每轮读结果：检查清单（建议逐项扫）

对每条 `row`：

1. **`caption`**  
   - 与 **`tag_groups.subject_content`** 是否一致（漏主体、错主体、只剩泛化标签）。

2. **互斥与冗余**（`composition_distance`、`scene_lighting`、`style_impression`）  
   - 例如：宽景 vs 近景、特写 vs 近景、夜间 vs 日间等，是否仍同时出现在 `tags` 或 `tag_groups`（最终应由 `_GROUP_LABEL_CONFLICTS` + `_filter_conflicting_labels` 消解）。

3. **人物相关**  
   - 多人是否仍带「单人肖像」；推车/劳动是否误判肖像；成人+婴儿是否只标「儿童」等。

4. **具体优先于泛化**  
   - `_SUBJECT_GENERIC_TO_SPECIFICS`、`_prefer_specific_subject_tags`、以及 refine 里针对 caption 的插入/删除（如城市 vs 城市天际线）。

5. **`errors`**  
   - 非空则先排环境问题（路径、解码、模型加载），再排逻辑。

可把「问题 → 对应文件/函数」记在 `technical_notes/ISSUES.md` 或本轮备注里，方便审计。

---

## 6. 校正（改代码）的推荐范围

| 区域 | 典型改动 |
|------|-----------|
| `photo_analyzer/core.py` → `_refine_tag_groups` | 基于 caption token / `has_phrase` 的语境规则（人物、花卉、劳动、亲子、天际线+桥等） |
| `photo_analyzer/core.py` → `_GROUP_LABEL_CONFLICTS` | 组内标签互斥表 |
| `photo_analyzer/core.py` → `_SUBJECT_GENERIC_TO_SPECIFICS` | 题材泛化在有具体标签时的降级 |
| `photo_analyzer/taxonomy.json` | 新增标签、trigger_terms（**谨慎**：条目多，改动了需确认 `load_taxonomy` 仍合法） |
| `tests/test_core.py` | **每个 bug 模式一条** `@patch generate_caption` 的回归测试，避免仅靠本地大图复现 |

**原则**（与项目惯例一致）：

- 单轮只解决 **1～2 类** 可描述清楚的问题，避免「顺手大重构」。  
- 逻辑尽量集中在 refine / 冲突表 / 具体优先，避免在多处复制相同判断。  
- 改完跑：`python3 -m unittest tests.test_core`（或项目约定的测试命令）。

---

## 7. 多轮闭环的标准节奏（交给 agent 的步骤模板）

1. **准备 manifest**（或确认已存在 `tmp_five_manifest.json`）。  
2. **Round 1**：`git_large` 跑满 manifest → 写入 `tmp_round_1_git_large.json`。  
3. **分析**：按第 5 节清单记录问题。  
4. **校正**：改 `core.py` / `taxonomy.json` + 加/改 `tests/test_core.py`。  
5. **单测通过**。  
6. **Round 2**：再次跑同一 manifest → `tmp_round_2_git_large.json`，对比 Round 1 的 `tag_groups` / `caption`。  
7. 若仍有新问题，重复 3～6；若连续多轮输出一致且无明显误判，可结束或换一批 manifest 继续做。  

**文档化**：建议在 PR 或内部说明里附上「本轮 manifest 种子、轮次、主要改动点」，便于回溯。

---

## 8. 常见问题

**Q：为什么用 `git_large` 而不是默认 `balanced`？**  
A：大模型 caption 更细、更长，更容易触发 refine 边缘情况；默认模型可作为补充对照，但不必每轮都跑双模型（除非用户要求）。

**Q：5 张会不会太少？**  
A：这是 **快速迭代** 用；可改为 20/100 张，但需延长单次运行时间，并仍建议 **固定 manifest**。

**Q：`tmp_*.json` 要不要提交 Git？**  
A：默认 **不提交**（含绝对路径与用户图信息）。若团队需要共享结果，可脱敏后放内部存储或只提交「文件名 + tag_groups 摘要」。

**Q：Swift App 要不要一起测？**  
A：本流程针对 **Python 分析管线**；App 若只是调用同一分析逻辑，以 CLI/单测为准即可；UI 联调另列清单。

---

## 9. 与本项目已有实践的对应关系

- 模型说明见 [MODELS.md](MODELS.md)。  
- 架构与数据流见 [ARCHITECTURE.md](ARCHITECTURE.md)。  
- 本文描述的流程曾在本仓库中用于：`git_large` + 固定 5 张 + 多轮 JSON 输出 + `core.py` 亲子/城市天际线/桥梁等 refine 校正（示例产物名：`tmp_five_manifest.json`、`tmp_round_*_git_large.json`）。

后续 agent **复制第 3～4 节脚本** 即可在干净环境中复现骨架；**第 5～7 节** 为质量与协作约定。

---

## 10. 附录：五轮各随机 5 张（子 agent 分文档 + 最后汇总改代码）

与第 1～7 节「**固定 manifest、每轮改一点**」并列的另一种流程：**每轮用不同种子随机抽 5 张**，每轮子 agent 只维护当轮 `round_XX_notes.md`（脚本会生成表格 + 启发式标记 + 待填 checklist），**全部跑完后**由汇总 agent 读 `SUMMARY.md` / 各轮笔记，再统一改 `core.py`。

### 10.1 自动化脚本

- 路径：`scripts/run_eval_five_rounds_random.py`  
- 项目根执行：

```bash
PYTHONPATH=. python3 scripts/run_eval_five_rounds_random.py
# 例如：10 轮 × 5 张，最快模型 fast（BLIP-base）
PYTHONPATH=. python3 scripts/run_eval_five_rounds_random.py --rounds 10 --model fast
```

- 图集目录：默认 `/Users/Noah/Pictures/分享输出`，可用 `--root` 或环境变量 **`PHOTO_ANALYZER_IMAGE_ROOT`** 覆盖。  
- 可选参数：`--rounds`、`--per-round`、`--model`（`fast` / `balanced` / `detailed` / `photo` / `git_large`）、`--base-seed`、`--out <目录>`。  
- 每轮结果文件名为 `round_XX_<model>.json`（例如 `round_01_fast.json`）。

### 10.2 产出目录结构（每次运行新建时间戳子目录）

```text
var/eval_runs/<YYYYMMDD_HHMMSS>_random_5x5/
  meta.json                 # 种子、耗时、启发式标记统计
  SUMMARY.md                # 跨轮汇总（重复文件、各轮文件名、后续步骤）
  round_01_manifest.json    # 第 1 轮绝对路径 + seed
  round_01_git_large.json   # 第 1 轮完整结果
  round_01_notes.md         # 第 1 轮表格 + 子 agent 待填
  ... round_02 ... round_05 ...
```

`var/`（含 `var/eval_runs/`）已列入仓库 **`.gitignore`**（含用户路径与描述文本）；需要留档时在本地复制 `SUMMARY.md` 脱敏后另存，或改 `--out` 到非忽略路径。

### 10.3 已做的一次示例跑通（本机）

- 命令：`PYTHONPATH=. python3 scripts/run_eval_five_rounds_random.py`  
- 结果目录：`var/eval_runs/20260330_094103_random_5x5/`（仅本机磁盘，不提交 Git；目录名仅为历史示例）  
- 规模：25 条推理，约 **129s**（CPU，`git_large` 单进程加载一次）  
- 启发式扫到：**题材为空** 2 条；25 张文件名跨轮无重复。  

子 agent 接手时：**先读该目录下 `SUMMARY.md` 与各 `round_XX_notes.md`**，在笔记里勾选/填写「人工误判」与「建议改动」，再进入实现阶段。
