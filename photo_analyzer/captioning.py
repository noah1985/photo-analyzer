from __future__ import annotations

import os
from functools import lru_cache

from PIL import Image


MODEL_ID = "Salesforce/blip-image-captioning-base"


class CaptioningError(RuntimeError):
    """Raised when local image captioning cannot run."""


def _dependencies_available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _caption_pipeline():
    if not _dependencies_available():
        raise CaptioningError(
            "本地图像描述模型不可用：缺少 PyTorch 或 transformers，已退回纯规则标签。"
        )

    import torch
    from transformers import pipeline

    device = 0 if torch.cuda.is_available() else -1
    return pipeline("image-to-text", model=MODEL_ID, device=device)


def generate_caption(image_path: str) -> str:
    override = os.environ.get("PHOTO_ANALYZER_CAPTION_OVERRIDE")
    if override:
        return override.strip()

    try:
        with Image.open(image_path) as image:
            rgb = image.convert("RGB")
            captioner = _caption_pipeline()
            output = captioner(rgb)
    except CaptioningError:
        raise
    except Exception as exc:  # pragma: no cover - runtime/model IO
        raise CaptioningError(f"本地图像描述失败：{exc}；已退回纯规则标签。") from exc

    if not output:
        raise CaptioningError("本地图像描述未返回结果，已退回纯规则标签。")

    text = str(output[0].get("generated_text", "")).strip()
    if not text:
        raise CaptioningError("本地图像描述为空，已退回纯规则标签。")
    return text
