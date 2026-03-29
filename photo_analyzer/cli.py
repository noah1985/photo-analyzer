from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from typing import Iterable

from .captioning import DEFAULT_MODEL_KEY, available_caption_models, preload_caption_pipeline
from .core import (
    ANALYSIS_VERSION,
    TAG_GROUP_LABELS,
    TAG_GROUP_ORDER,
    AnalysisError,
    AnalysisResult,
    analyze_image,
)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
DEFAULT_SAMPLE_COUNT = 100
DEFAULT_SAMPLE_SEED = 20260421
CAPTION_MODEL_CHOICES = [spec.key for spec in available_caption_models()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="photo-analyzer",
        description="本地图片分析工具（本地模型优先，HTML 保持轻量前端规则分析）",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"photo-analyzer {ANALYSIS_VERSION}",
    )
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser("analyze", help="分析单张图片或一个目录中的多张图片")
    analyze.add_argument("image_path", help="图片路径或目录路径")
    analyze.add_argument(
        "--model",
        choices=CAPTION_MODEL_CHOICES,
        default=DEFAULT_MODEL_KEY,
        help=f"本地图像描述模型预设，默认 {DEFAULT_MODEL_KEY}",
    )

    sample_gallery = subparsers.add_parser(
        "sample-gallery", help="随机抽样图片并导出静态标签画廊"
    )
    sample_gallery.add_argument("image_path", help="图片目录路径")
    sample_gallery.add_argument(
        "--count",
        type=int,
        default=DEFAULT_SAMPLE_COUNT,
        help=f"抽样数量，默认 {DEFAULT_SAMPLE_COUNT}，最大 100",
    )
    sample_gallery.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SAMPLE_SEED,
        help=f"随机种子，默认 {DEFAULT_SAMPLE_SEED}",
    )
    sample_gallery.add_argument(
        "--output-dir",
        default="sample_gallery_output",
        help="导出目录，默认 sample_gallery_output",
    )
    sample_gallery.add_argument(
        "--model",
        choices=CAPTION_MODEL_CHOICES,
        default=DEFAULT_MODEL_KEY,
        help=f"本地图像描述模型预设，默认 {DEFAULT_MODEL_KEY}",
    )

    analyze_dir = subparsers.add_parser(
        "analyze-dir", help="分析目录中的图片，输出 JSON 到 stdout（供 Swift App 调用）"
    )
    analyze_dir.add_argument("image_path", help="图片目录路径")
    analyze_dir.add_argument(
        "--count",
        type=int,
        default=DEFAULT_SAMPLE_COUNT,
        help=f"抽样数量，默认 {DEFAULT_SAMPLE_COUNT}，最大 100",
    )
    analyze_dir.add_argument(
        "--seed",
        type=int,
        default=None,
        help="随机种子；不传则每次抽样顺序不同（随机）",
    )
    analyze_dir.add_argument(
        "--stream",
        action="store_true",
        default=False,
        help="逐张输出 JSONL（每行一个 JSON），供 GUI 实时读取进度",
    )
    analyze_dir.add_argument(
        "--model",
        choices=CAPTION_MODEL_CHOICES,
        default=DEFAULT_MODEL_KEY,
        help=f"本地图像描述模型预设，默认 {DEFAULT_MODEL_KEY}",
    )

    subparsers.add_parser("app", help="启动本地桌面标签画廊，无需 web service")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "analyze-dir":
        return run_analyze_dir(args)

    if args.command == "sample-gallery":
        return run_sample_gallery(args)

    if args.command == "app":
        from .desktop_app import main as run_desktop_app

        return run_desktop_app()

    if args.command != "analyze":
        parser.print_help()
        return 1

    try:
        targets = collect_targets(args.image_path)
    except AnalysisError as exc:
        print(f"分析失败：{exc}", file=sys.stderr)
        return 1

    failures = 0
    for index, target in enumerate(targets):
        try:
            result = analyze_image(str(target), model_key=args.model)
        except AnalysisError as exc:
            failures += 1
            print(f"[{target.name}] 分析失败：{exc}", file=sys.stderr)
            continue

        if len(targets) > 1:
            if index:
                print()
            print(f"=== {target.name} ===")
        print(format_result(result))

    return 0 if failures == 0 else 1


def run_analyze_dir(args: argparse.Namespace) -> int:
    """Analyze a directory, output JSON to stdout (machine-readable for Swift App)."""
    if args.count < 1 or args.count > 100:
        error = {"ok": False, "error": "抽样数量必须在 1-100 之间"}
        print(json.dumps(error, ensure_ascii=False))
        return 1

    source_dir = Path(args.image_path).expanduser().resolve()
    if not source_dir.is_dir():
        error = {"ok": False, "error": f"不是有效的目录：{source_dir}"}
        print(json.dumps(error, ensure_ascii=False))
        return 1

    try:
        targets = collect_targets(str(source_dir))
    except AnalysisError as exc:
        error = {"ok": False, "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False))
        return 1

    chosen = sample_targets(targets, args.count, args.seed, sort_by_name=False)
    stream = getattr(args, "stream", False)

    if stream:
        return _run_analyze_dir_stream(chosen, source_dir, args.count, len(targets), args.model)

    items = []
    failures = []
    for target in chosen:
        try:
            result = analyze_image(str(target), model_key=args.model)
        except AnalysisError as exc:
            failures.append({"file_name": target.name, "file_path": str(target), "error": str(exc)})
            continue
        items.append(build_gallery_item(result))

    payload = {
        "ok": True,
        "source_directory": str(source_dir),
        "sample_count": len(items),
        "requested_count": min(args.count, len(targets)),
        "caption_model": args.model,
        "analysis_version": ANALYSIS_VERSION,
        "items": items,
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _emit(obj: dict[str, object]) -> None:
    """Write a single JSONL line and immediately flush."""
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _run_analyze_dir_stream(
    chosen: list[Path], source_dir: Path, requested_count: int, available_count: int, model_key: str
) -> int:
    total = len(chosen)
    _emit({
        "type": "start",
        "total": total,
        "source_directory": str(source_dir),
        "requested_count": min(requested_count, available_count),
        "files": [{"file_name": t.name, "file_path": str(t)} for t in chosen],
    })

    _emit({"type": "model_loading", "caption_model": model_key})
    init_sec = 0.0
    try:
        init_sec = preload_caption_pipeline(model_key)
    except Exception:  # pragma: no cover - 预加载失败时首张 analyze 仍会重试
        init_sec = 0.0
    _emit({"type": "model_ready", "model_initialization_seconds": init_sec})

    success_count = 0
    fail_count = 0
    for index, target in enumerate(chosen):
        _emit({
            "type": "progress",
            "index": index,
            "file_name": target.name,
            "file_path": str(target),
        })
        try:
            result = analyze_image(str(target), model_key=model_key)
            item = build_gallery_item(result)
            _emit({"type": "result", "index": index, **item})
            success_count += 1
        except AnalysisError as exc:
            _emit({"type": "error", "index": index, "file_name": target.name,
                    "file_path": str(target), "error": str(exc)})
            fail_count += 1

    _emit({"type": "done", "total_success": success_count, "total_failed": fail_count})
    return 0


def run_sample_gallery(args: argparse.Namespace) -> int:
    if args.count < 1:
        print("分析失败：抽样数量必须大于 0", file=sys.stderr)
        return 1
    if args.count > 100:
        print("分析失败：抽样数量不能超过 100", file=sys.stderr)
        return 1

    source_dir = Path(args.image_path).expanduser().resolve()
    if not source_dir.exists():
        print(f"分析失败：文件不存在：{source_dir}", file=sys.stderr)
        return 1
    if not source_dir.is_dir():
        print(f"分析失败：不是有效的目录：{source_dir}", file=sys.stderr)
        return 1

    try:
        targets = collect_targets(str(source_dir))
    except AnalysisError as exc:
        print(f"分析失败：{exc}", file=sys.stderr)
        return 1

    chosen = sample_targets(targets, args.count, args.seed, sort_by_name=True)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    items = []
    failures = []
    for target in chosen:
        try:
            result = analyze_image(str(target), model_key=args.model)
        except AnalysisError as exc:
            failures.append({"file_name": target.name, "file_path": str(target), "error": str(exc)})
            continue
        items.append(build_gallery_item(result))

    payload = {
        "source_directory": str(source_dir),
        "sample_count": len(items),
        "requested_count": min(args.count, len(targets)),
        "seed": args.seed,
        "caption_model": args.model,
        "generated_at": generated_at,
        "analysis_version": ANALYSIS_VERSION,
        "items": items,
        "failures": failures,
    }

    json_path = output_dir / "results.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    html_path = output_dir / "index.html"
    html_path.write_text(render_gallery_html(payload, output_dir), encoding="utf-8")

    print(f"已生成 JSON：{json_path}")
    print(f"已生成 HTML：{html_path}")
    print(f"抽样图片数：{len(items)}")
    if failures:
        print(f"失败图片数：{len(failures)}")
    return 0


def collect_targets(input_path: str) -> list[Path]:
    path = Path(input_path).expanduser().resolve()
    if not path.exists():
        raise AnalysisError(f"文件不存在：{path}")

    if path.is_file():
        return [path]

    if not path.is_dir():
        raise AnalysisError(f"不是有效的文件或目录：{path}")

    targets = sorted(
        candidate
        for candidate in path.iterdir()
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not targets:
        raise AnalysisError(f"目录中没有可分析的图片：{path}")
    return targets


def sample_targets(
    targets: list[Path], count: int, seed: int | None, *, sort_by_name: bool = True
) -> list[Path]:
    if len(targets) <= count:
        return sorted(targets)
    rng = Random(seed) if seed is not None else Random()
    chosen = rng.sample(targets, count)
    if sort_by_name:
        return sorted(chosen, key=lambda path: path.name)
    return chosen


def build_gallery_item(result: AnalysisResult) -> dict[str, object]:
    return {
        "file_name": Path(result.image.path).name,
        "file_path": result.image.path,
        "summary": result.summary,
        "caption": result.caption,
        "caption_model": result.caption_model,
        "caption_model_label": result.caption_model_label,
        "model_initialization_seconds": result.model_initialization_seconds,
        "analysis_duration_seconds": result.analysis_duration_seconds,
        "tag_groups": result.tag_groups,
        "tags": result.tags or ["无描述标签"],
    }


def format_result(result: AnalysisResult) -> str:
    lines = [
        f"总体判断：{result.summary}",
        "",
        "文件信息：",
        f"- 路径：{result.image.path}",
        f"- 格式：{result.image.format}",
        f"- 尺寸：{result.image.width} x {result.image.height}",
        f"- 方向：{result.image.orientation}",
        f"- 宽高比：{result.image.aspect_ratio}",
        "",
        "基础指标：",
        f"- 亮度：{result.metrics.brightness}",
        f"- 对比度：{result.metrics.contrast}",
        f"- 饱和度：{result.metrics.saturation}",
        f"- 冷暖倾向：{result.metrics.temperature}",
        f"- 清晰度：{result.metrics.sharpness}",
        "",
        "分析信息：",
        f"- 模型：{result.caption_model_label} ({result.caption_model})",
        f"- 模型初始化：{result.model_initialization_seconds} 秒",
        f"- 耗时：{result.analysis_duration_seconds} 秒",
    ]
    for group_name in TAG_GROUP_ORDER:
        group_tags = result.tag_groups.get(group_name, [])
        if not group_tags:
            continue
        lines.extend(["", f"{TAG_GROUP_LABELS[group_name]}：", f"- {'、'.join(group_tags)}"])
    if result.caption:
        lines.extend(["", "本地模型描述：", f"- {result.caption}"])
    if result.errors:
        lines.extend(["", "提示：", *[f"- {message}" for message in result.errors]])
    return "\n".join(lines)


def render_gallery_html(payload: dict[str, object], output_dir: Path) -> str:
    items = payload["items"]
    source_directory = str(payload["source_directory"])
    sample_count = int(payload["sample_count"])
    requested_count = int(payload["requested_count"])
    seed = int(payload["seed"])
    generated_at = str(payload["generated_at"])
    failures = payload.get("failures", [])

    cards = "\n".join(render_gallery_card(item, output_dir) for item in items)
    source_directory_escaped = html.escape(source_directory)
    source_command = source_directory.replace("\\", "\\\\").replace('"', '\\"')
    output_command = str(output_dir).replace("\\", "\\\\").replace('"', '\\"')
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Photo Analyzer Sample Gallery</title>
  <style>
    :root {{
      --bg: #f4f0e8;
      --surface: #fffaf3;
      --text: #1d1b18;
      --muted: #6f665d;
      --accent: #274e3f;
      --border: #ddd2c1;
      --tag-bg: #efe5d6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "PingFang SC", "Noto Sans CJK SC", sans-serif;
      background: linear-gradient(180deg, #fffaf0 0%, var(--bg) 70%, #ebe1d5 100%);
      color: var(--text);
    }}
    .page {{
      width: min(1420px, calc(100vw - 32px));
      margin: 24px auto 48px;
    }}
    .panel {{
      background: color-mix(in srgb, var(--surface) 92%, white 8%);
      border: 1px solid var(--border);
      border-radius: 22px;
      padding: 22px;
      box-shadow: 0 18px 42px rgba(42, 34, 24, 0.08);
    }}
    .header {{
      display: grid;
      gap: 18px;
      margin-bottom: 22px;
    }}
    .meta {{
      display: grid;
      gap: 6px;
      font-size: 14px;
      line-height: 1.5;
      color: var(--muted);
    }}
    .control-bar {{
      display: grid;
      grid-template-columns: minmax(0, 240px) auto;
      gap: 12px;
      align-items: end;
    }}
    .control-group {{
      display: grid;
      gap: 8px;
    }}
    .control-group label {{
      font-size: 14px;
      color: var(--muted);
    }}
    .control-group input {{
      height: 44px;
      border-radius: 12px;
      border: 1px solid var(--border);
      padding: 0 14px;
      background: white;
      font-size: 15px;
    }}
    button {{
      height: 44px;
      border: none;
      border-radius: 12px;
      background: var(--accent);
      color: white;
      font-size: 15px;
      padding: 0 18px;
      cursor: pointer;
    }}
    .command-box {{
      display: grid;
      gap: 8px;
    }}
    .hint {{
      font-size: 13px;
      color: var(--muted);
    }}
    .command-box textarea {{
      width: 100%;
      min-height: 72px;
      resize: vertical;
      border-radius: 12px;
      border: 1px solid var(--border);
      padding: 12px;
      font: 13px/1.5 "SFMono-Regular", Menlo, Consolas, monospace;
      background: #fffdf9;
      color: var(--text);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
      gap: 18px;
    }}
    .card {{
      background: color-mix(in srgb, var(--surface) 94%, white 6%);
      border: 1px solid var(--border);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 14px 30px rgba(40, 33, 24, 0.08);
    }}
    .thumb {{
      aspect-ratio: 4 / 3;
      background: #ddd4c7;
    }}
    .thumb img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .content {{
      display: grid;
      gap: 12px;
      padding: 14px;
    }}
    .file-name {{
      font-size: 14px;
      font-weight: 600;
      line-height: 1.4;
      word-break: break-word;
    }}
    .summary {{
      font-size: 13px;
      line-height: 1.5;
      color: var(--muted);
    }}
    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .tag {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 10px;
      border-radius: 999px;
      background: var(--tag-bg);
      color: #4c4035;
      font-size: 13px;
      line-height: 1.2;
    }}
    @media (max-width: 720px) {{
      .control-bar {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="panel header">
      <div>
        <h1>抽样标签画廊</h1>
      </div>
      <div class="meta">
        <div>源目录：{source_directory_escaped}</div>
        <div>本次抽样：{sample_count} 张，目标数量：{requested_count} 张，随机种子：{seed}</div>
        <div>生成时间：{html.escape(generated_at)}</div>
        <div>失败图片数：{len(failures)}</div>
      </div>
      <div class="control-bar">
        <div class="control-group">
          <label for="sample-count">测试照片数（最大 100）</label>
          <input id="sample-count" type="number" min="1" max="100" value="{min(requested_count, 100)}">
        </div>
        <button id="generate-command" type="button">生成抽样结果</button>
      </div>
      <div class="command-box">
        <div class="hint">静态页面不能直接执行本地程序。点击按钮会生成建议命令，在终端运行后可更新当前画廊。</div>
        <textarea id="command-output" readonly></textarea>
      </div>
    </section>
    <section class="grid">
      {cards}
    </section>
  </div>
  <script>
    const input = document.getElementById('sample-count');
    const output = document.getElementById('command-output');
    const button = document.getElementById('generate-command');
    const sourceDirectory = "{source_command}";
    const outputDirectory = "{output_command}";
    const seed = {seed};

    function buildCommand() {{
      const raw = Number.parseInt(input.value || "100", 10);
      const count = Number.isFinite(raw) ? Math.min(100, Math.max(1, raw)) : 100;
      input.value = String(count);
      output.value = `python3 -m photo_analyzer sample-gallery "${{sourceDirectory}}" --count ${{count}} --seed ${{seed}} --output-dir "${{outputDirectory}}"`;
    }}

    button.addEventListener('click', buildCommand);
    buildCommand();
  </script>
</body>
</html>
"""


def render_gallery_card(item: dict[str, object], output_dir: Path) -> str:
    image_path = Path(str(item["file_path"]))
    try:
        image_src = image_path.relative_to(output_dir.parent)
    except ValueError:
        image_src = image_path

    tags = item["tags"] or ["无描述标签"]
    tags_html = "".join(f'<span class="tag">{html.escape(str(tag))}</span>' for tag in tags)
    summary = html.escape(str(item.get("summary", "")))
    return f"""
      <article class="card">
        <div class="thumb">
          <img src="{html.escape(image_src.as_posix())}" alt="{html.escape(str(item["file_name"]))}">
        </div>
        <div class="content">
          <div class="file-name">{html.escape(str(item["file_name"]))}</div>
          <div class="summary">{summary}</div>
          <div class="tags">{tags_html}</div>
        </div>
      </article>
    """
