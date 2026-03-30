#!/usr/bin/env python3
"""
多轮 × 每轮随机 N 张图，可选 caption 模型，落盘 manifest / JSON / 每轮笔记，并生成 SUMMARY.md。

用法（项目根目录）：
  PYTHONPATH=. python3 scripts/run_eval_five_rounds_random.py
  PYTHONPATH=. python3 scripts/run_eval_five_rounds_random.py --rounds 10 --model blip_base --root /path/to/photos

环境变量 PHOTO_ANALYZER_IMAGE_ROOT 可覆盖默认图集根目录。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any

# 默认图集根目录；可用参数或环境变量覆盖
_DEFAULT_IMAGE_ROOT = "/Users/Noah/Pictures/分享输出"
_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".JPG", ".JPEG", ".PNG", ".WEBP"}


def _list_images(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.iterdir()
        if p.is_file() and p.suffix in _EXTS and not p.name.startswith(".")
    )


def _flags_for_row(row: dict[str, Any]) -> list[str]:
    tg = row.get("tag_groups") or {}
    subj = tg.get("subject_content") or []
    comp = set(tg.get("composition_distance") or [])
    tags = set(row.get("tags") or [])
    caps = (row.get("caption") or "").lower()
    out: list[str] = []
    if not subj:
        out.append("题材为空")
    wide = comp & {"宽景"}
    close = comp & {"近景", "特写"}
    if wide and close:
        out.append("构图_宽景与近特并存")
    if "特写" in comp and "近景" in comp:
        out.append("构图_特写与近景并存")
    scene = set(tg.get("scene_lighting") or [])
    if "室内" in scene and "室外" in scene:
        out.append("光线_室内外并存")
    if "夜景" in scene and "日落" in scene:
        out.append("光线_夜景与日落并存")
    return out


def _write_round_notes(
    out_dir: Path, round_idx: int, rows: list[dict[str, Any]], elapsed: float, model_key: str
) -> None:
    lines = [
        f"# 第 {round_idx} 轮笔记（随机 {len(rows)} 张 × `{model_key}`）",
        "",
        f"- 本轮推理耗时（约）：**{elapsed:.1f}s**",
        "",
        "## 样本结果",
        "",
        "| 文件 | 题材 | 构图 | 标记 |",
        "|------|------|------|------|",
    ]
    for row in rows:
        tg = row["tag_groups"]
        subj = "、".join(tg.get("subject_content") or []) or "—"
        comp = "、".join(tg.get("composition_distance") or []) or "—"
        fl = _flags_for_row(row)
        flag_cell = "；".join(fl) if fl else "—"
        cap = (row.get("caption") or "")[:100].replace("|", "\\|")
        name = Path(row["path"]).name
        lines.append(f"| `{name}` | {subj} | {comp} | {flag_cell} |")
        lines.append(f"| | *caption:* {cap}… | | |")
    lines.append("")
    lines.append("## 子 agent 待填（可选）")
    lines.append("")
    lines.append("- [ ] 人工认为明显误判：")
    lines.append("- [ ] 建议改 `core.py` / taxonomy：")
    lines.append("")
    (out_dir / f"round_{round_idx:02d}_notes.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    from photo_analyzer.captioning import CLI_MODEL_CHOICES

    parser = argparse.ArgumentParser(description="多轮随机抽样 caption 评测")
    parser.add_argument(
        "--root",
        default=os.environ.get("PHOTO_ANALYZER_IMAGE_ROOT", _DEFAULT_IMAGE_ROOT),
        type=Path,
        help="图集目录（平铺图片）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出目录（默认 var/eval_runs/<timestamp>_random_<R>x<P>_<model>）",
    )
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--per-round", type=int, default=5)
    parser.add_argument("--base-seed", type=int, default=202603301)
    parser.add_argument(
        "--model",
        type=str,
        default="blip2_6_7b",
        choices=sorted(CLI_MODEL_CHOICES),
        help="caption 模型预设（最快为 blip_base）",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"图集目录不存在：{root}")

    images = _list_images(root)
    if len(images) < args.per_round:
        raise SystemExit(f"图片不足 {args.per_round} 张：{root}（当前 {len(images)}）")

    repo_root = Path(__file__).resolve().parents[1]
    if args.out is None:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out_dir = (
            repo_root
            / "var"
            / "eval_runs"
            / f"{stamp}_random_{args.rounds}x{args.per_round}_{args.model}"
        )
    else:
        out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    os.chdir(repo_root)
    # 延迟导入，确保 cwd 在 repo（相对 taxonomy）
    from photo_analyzer.core import analyze_image

    all_rows: list[dict[str, Any]] = []
    round_summaries: list[dict[str, Any]] = []
    t_all = time.perf_counter()

    for r in range(1, args.rounds + 1):
        random.seed(args.base_seed + r)
        picked = random.sample(images, args.per_round)
        manifest = [str(p.resolve()) for p in picked]
        (out_dir / f"round_{r:02d}_manifest.json").write_text(
            json.dumps(
                {"round": r, "seed": args.base_seed + r, "paths": manifest},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        rows: list[dict[str, Any]] = []
        t0 = time.perf_counter()
        for p in picked:
            res = analyze_image(str(p), model_key=args.model)
            rows.append(
                {
                    "path": str(p.resolve()),
                    "caption": res.caption,
                    "caption_model": res.caption_model,
                    "tag_groups": res.tag_groups,
                    "tags": res.tags,
                    "errors": res.errors,
                }
            )
        elapsed = time.perf_counter() - t0

        results_name = f"round_{r:02d}_{args.model}.json"
        (out_dir / results_name).write_text(
            json.dumps(
                {
                    "round": r,
                    "model": args.model,
                    "elapsed_s": round(elapsed, 2),
                    "rows": rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _write_round_notes(out_dir, r, rows, elapsed, args.model)

        flags_flat: list[str] = []
        for row in rows:
            flags_flat.extend(_flags_for_row(row))
        round_summaries.append(
            {
                "round": r,
                "seed": args.base_seed + r,
                "elapsed_s": round(elapsed, 2),
                "files": [Path(x).name for x in manifest],
                "flag_counts": dict(Counter(flags_flat)),
            }
        )
        all_rows.extend(rows)

    total_elapsed = time.perf_counter() - t_all
    names = [Path(r["path"]).name for r in all_rows]
    name_counts = Counter(names)
    duped = {k: v for k, v in name_counts.items() if v > 1}
    all_flags: list[str] = []
    for row in all_rows:
        all_flags.extend(_flags_for_row(row))
    flag_total = Counter(all_flags)

    total_infer = len(all_rows)
    summary_lines = [
        "# 多轮随机抽样实验汇总",
        "",
        "## 元数据",
        "",
        f"- 图集根目录：`{root}`",
        f"- 模型：`{args.model}`",
        f"- 轮数：{args.rounds}，每轮 {args.per_round} 张，共 **{total_infer}** 条推理",
        f"- 不重复文件数：**{len(name_counts)}**（跨轮重复见下表）",
        f"- 随机种子：`base_seed={args.base_seed}`，第 r 轮使用 `base_seed + r`",
        f"- 总耗时（含加载）：**{total_elapsed:.1f}s**",
        f"- 输出目录：`{out_dir.relative_to(repo_root)}`",
        "",
        "## 跨轮重复出现的文件",
        "",
        "若同一文件在多轮被抽中，便于观察 caption/标签方差。",
        "",
    ]
    if duped:
        summary_lines.append("| 文件名 | 出现次数 |")
        summary_lines.append("|--------|----------|")
        for name, cnt in sorted(duped.items(), key=lambda x: -x[1]):
            summary_lines.append(f"| `{name}` | {cnt} |")
    else:
        summary_lines.append(f"*本轮 {total_infer} 条样本文件名均无重复。*")
    summary_lines.extend(
        [
            "",
            f"## 自动启发式标记统计（{total_infer} 条合计）",
            "",
            "用于快速扫问题；**非完整质检**。",
            "",
            "| 标记 | 次数 |",
            "|------|------|",
        ]
    )
    for label, cnt in flag_total.most_common():
        summary_lines.append(f"| {label} | {cnt} |")
    if not flag_total:
        summary_lines.append("| — | 0 |")
    summary_lines.extend(
        [
            "",
            "## 各轮摘要",
            "",
            "| 轮次 | seed | 耗时(s) | 本轮文件名 |",
            "|------|------|---------|------------|",
        ]
    )
    for s in round_summaries:
        files = " ".join(f"`{f}`" for f in s["files"])
        summary_lines.append(
            f"| {s['round']} | {s['seed']} | {s['elapsed_s']} | {files} |"
        )
    summary_lines.extend(
        [
            "",
            "## 后续（汇总后再改代码）",
            "",
            "1. 人工过一遍每轮 `round_XX_notes.md` 中的 caption 行。",
            "2. 将共性问题写入 `FINDINGS.md`（可另建）并排序优先级。",
            "3. 由实现 agent 改 `photo_analyzer/core.py` / `taxonomy.json` 并补 `tests/test_core.py`。",
            "4. 可选：用本目录下各 `round_XX_manifest.json` 再跑一轮做回归。",
            "",
        ]
    )
    (out_dir / "SUMMARY.md").write_text("\n".join(summary_lines), encoding="utf-8")
    (out_dir / "meta.json").write_text(
        json.dumps(
            {
                "image_root": str(root),
                "model": args.model,
                "rounds": args.rounds,
                "per_round": args.per_round,
                "base_seed": args.base_seed,
                "total_elapsed_s": round(total_elapsed, 2),
                "unique_files": len(name_counts),
                "duplicate_names": duped,
                "flag_counts": dict(flag_total),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Done. Output: {out_dir}")


if __name__ == "__main__":
    main()
