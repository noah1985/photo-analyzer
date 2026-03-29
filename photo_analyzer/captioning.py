from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

@dataclass(frozen=True)
class CaptionModelSpec:
    key: str
    label: str
    model_id: str
    capability: str
    speed: str
    mode: str = "caption"


ProgressCallback = Callable[[dict[str, object]], None]


MODEL_SPECS = {
    "fast": CaptionModelSpec(
        key="fast",
        label="快速",
        model_id="Salesforce/blip-image-captioning-base",
        capability="主体识别基础稳定，适合快速初筛。",
        speed="CPU 下通常 2-4 秒/张。",
    ),
    "balanced": CaptionModelSpec(
        key="balanced",
        label="平衡",
        model_id="Salesforce/blip-image-captioning-large",
        capability="主体和场景判断更稳，适合作为默认模型。",
        speed="CPU 下通常 3-8 秒/张。",
    ),
    "detailed": CaptionModelSpec(
        key="detailed",
        label="细节",
        model_id="nlpconnect/vit-gpt2-image-captioning",
        capability="描述更开放，细节词更多，但偶尔会更发散。",
        speed="CPU 下通常 4-9 秒/张。",
    ),
    "photo": CaptionModelSpec(
        key="photo",
        label="摄影",
        model_id="microsoft/git-base-coco",
        capability="摄影向 caption 补充（GIT COCO），可试；默认仍建议优先用平衡。",
        speed="CPU 下通常 4-12 秒/张。",
    ),
}
DEFAULT_MODEL_KEY = "balanced"


class CaptioningError(RuntimeError):
    """Raised when local image captioning cannot run."""


def available_caption_models() -> list[CaptionModelSpec]:
    return [MODEL_SPECS[key] for key in ("fast", "balanced", "detailed", "photo")]


def resolve_model_spec(model_key: str | None) -> CaptionModelSpec:
    key = (model_key or DEFAULT_MODEL_KEY).strip().lower()
    if key not in MODEL_SPECS:
        raise CaptioningError(f"未知模型预设：{key}")
    return MODEL_SPECS[key]


def _dependencies_available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


def _clean_caption(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.strip())
    compact = re.sub(r"\b(\w+)(?: \1){2,}\b", r"\1", compact, flags=re.IGNORECASE)

    words = compact.split(" ")
    if len(words) > 28:
        compact = " ".join(words[:28]).strip(" ,.;:")
        words = compact.split(" ")

    if len(words) >= 4:
        unique_ratio = len({word.lower() for word in words}) / len(words)
        if unique_ratio < 0.45:
            raise CaptioningError("本地图像描述失真，已退回纯规则标签。")

    if compact.lower().startswith("a photo of "):
        compact = compact[11:]
    elif compact.lower().startswith("an image of "):
        compact = compact[12:]

    compact = compact.strip(" ,.;:")
    if not compact:
        raise CaptioningError("本地图像描述为空，已退回纯规则标签。")
    return compact


_PIPELINE_CACHE: dict[str, object] = {}
_LAST_INIT_SECONDS: dict[str, float] = {}


def _emit_progress(callback: ProgressCallback | None, payload: dict[str, object]) -> None:
    if callback is not None:
        callback(payload)


def _ensure_model_downloaded(spec: CaptionModelSpec, progress_callback: ProgressCallback | None = None) -> str:
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    from tqdm.auto import tqdm

    class ProgressTqdm(tqdm):
        _callback: ProgressCallback | None = None
        _last_emit_at: float = 0.0

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._maybe_emit(force=True)

        def update(self, n=1):
            value = super().update(n)
            self._maybe_emit()
            return value

        def close(self):
            self._maybe_emit(force=True)
            return super().close()

        def _maybe_emit(self, force: bool = False) -> None:
            now = time.time()
            if not force and now - self._last_emit_at < 0.25:
                return
            self._last_emit_at = now
            total = float(self.total or 0)
            current = float(self.n or 0)
            percent = round((current / total) * 100, 1) if total > 0 else None
            eta_seconds = None
            remaining = self.format_dict.get("remaining")
            if remaining is not None:
                try:
                    eta_seconds = float(remaining)
                except (TypeError, ValueError):
                    eta_seconds = None
            callback = type(self)._callback
            if callback:
                callback(
                    {
                        "phase": "download",
                        "status": str(self.desc or spec.model_id),
                        "current": current,
                        "total": total if total > 0 else None,
                        "percent": percent,
                        "eta_seconds": eta_seconds,
                    }
                )

    ProgressTqdm._callback = progress_callback

    try:
        local_path = snapshot_download(
            repo_id=spec.model_id,
            local_files_only=True,
        )
        _emit_progress(
            progress_callback,
            {"phase": "cache", "status": "已命中本地模型缓存"},
        )
        return local_path
    except LocalEntryNotFoundError:
        pass

    return snapshot_download(
        repo_id=spec.model_id,
        resume_download=True,
        tqdm_class=ProgressTqdm,
    )


def _caption_pipeline(model_key: str, progress_callback: ProgressCallback | None = None):
    if not _dependencies_available():
        raise CaptioningError("本地图像描述模型不可用：缺少 PyTorch 或 transformers，已退回纯规则标签。")

    spec = resolve_model_spec(model_key)
    if spec.key in _PIPELINE_CACHE:
        _LAST_INIT_SECONDS[spec.key] = 0.0
        return _PIPELINE_CACHE[spec.key]

    started_at = time.perf_counter()
    local_path = _ensure_model_downloaded(spec, progress_callback)
    _emit_progress(progress_callback, {"phase": "load", "status": "正在加载模型到内存"})
    import torch
    from transformers import pipeline

    device = 0 if torch.cuda.is_available() else -1
    loaded = pipeline("image-to-text", model=local_path, device=device)
    _PIPELINE_CACHE[spec.key] = loaded
    _LAST_INIT_SECONDS[spec.key] = round(time.perf_counter() - started_at, 2)
    return loaded


def consume_last_model_init_seconds(model_key: str | None) -> float:
    spec = resolve_model_spec(model_key)
    return _LAST_INIT_SECONDS.pop(spec.key, 0.0)


def preload_caption_pipeline(model_key: str | None = None, progress_callback: ProgressCallback | None = None) -> float:
    if not _dependencies_available():
        return 0.0
    try:
        spec = resolve_model_spec(model_key)
    except CaptioningError:
        return 0.0
    if spec.key in _PIPELINE_CACHE:
        return 0.0
    try:
        _caption_pipeline(spec.key, progress_callback)
    except CaptioningError:
        return 0.0
    return consume_last_model_init_seconds(spec.key)


def generate_caption(image_path: str, model_key: str | None = None) -> str:
    override = os.environ.get("PHOTO_ANALYZER_CAPTION_OVERRIDE")
    if override:
        return _clean_caption(override)

    spec = resolve_model_spec(model_key)
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            rgb = image.convert("RGB")
            captioner = _caption_pipeline(spec.key)
            output = captioner(rgb, max_new_tokens=32)
    except CaptioningError:
        raise
    except Exception as exc:  # pragma: no cover - runtime/model IO
        raise CaptioningError(f"本地图像描述失败：{exc}；已退回纯规则标签。") from exc

    if not output:
        raise CaptioningError("本地图像描述未返回结果，已退回纯规则标签。")

    text = str(output[0].get("generated_text", "")).strip()
    if not text:
        raise CaptioningError("本地图像描述为空，已退回纯规则标签。")
    return _clean_caption(text)
