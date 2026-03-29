#!/usr/bin/env python3
"""将 caption 所需 HF 模型快照下载到项目 models/hf/（默认走 hf-mirror.com）。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 项目根（scripts/ 的上一级）
REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = REPO_ROOT / "models" / "hf"

# 与 photo_analyzer.captioning.VENDOR_DIR_NAMES 保持一致
REPO_SNAPSHOTS: list[tuple[str, str]] = [
    ("Salesforce/blip-image-captioning-base", "Salesforce_blip-image-captioning-base"),
    ("Salesforce/blip-image-captioning-large", "Salesforce_blip-image-captioning-large"),
    ("nlpconnect/vit-gpt2-image-captioning", "nlpconnect_vit-gpt2-image-captioning"),
    ("Salesforce/blip2-opt-2.7b", "Salesforce_blip2-opt-2.7b"),
    ("Salesforce/blip2-opt-6.7b", "Salesforce_blip2-opt-6.7b"),
]

PRESET_TO_REPO: dict[str, tuple[str, str]] = {
    "fast": REPO_SNAPSHOTS[0],
    "balanced": REPO_SNAPSHOTS[1],
    "detailed": REPO_SNAPSHOTS[2],
    "photo": REPO_SNAPSHOTS[3],
    "git_large": REPO_SNAPSHOTS[4],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="下载模型到 models/hf/（默认国内镜像）")
    parser.add_argument(
        "--only",
        action="append",
        choices=sorted(PRESET_TO_REPO.keys()),
        help="只下载指定预设（可多次指定），例如 --only photo",
    )
    parser.add_argument(
        "--endpoint",
        default="",
        help="覆盖 HF 端点，默认未设置时用 https://hf-mirror.com",
    )
    args = parser.parse_args()

    mirror = (args.endpoint or os.environ.get("HF_ENDPOINT", "").strip() or "https://hf-mirror.com").rstrip("/")
    os.environ["HF_ENDPOINT"] = mirror
    print(f"HF_ENDPOINT={os.environ['HF_ENDPOINT']}", file=sys.stderr)

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        print("请先安装：pip install huggingface_hub", file=sys.stderr)
        raise SystemExit(1) from exc

    VENDOR_ROOT.mkdir(parents=True, exist_ok=True)

    todo: list[tuple[str, str]]
    if args.only:
        todo = [PRESET_TO_REPO[k] for k in args.only]
    else:
        todo = list(REPO_SNAPSHOTS)

    for repo_id, dirname in todo:
        dest = VENDOR_ROOT / dirname
        print(f"==> {repo_id}\n    -> {dest}", file=sys.stderr)
        snapshot_download(repo_id=repo_id, local_dir=str(dest))
    print("完成。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
