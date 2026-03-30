from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class CaptionModelSpec:
    key: str
    label: str
    model_id: str
    capability: str
    speed: str
    mode: str = "caption"
    max_new_tokens: int = 32


ProgressCallback = Callable[[dict[str, object]], None]

# 与 scripts/vend_hf_models.py 中子目录名一致（项目 models/hf/<name>）
VENDOR_DIR_NAMES: dict[str, str] = {
    "blip_base": "Salesforce_blip-image-captioning-base",
    "blip_large": "Salesforce_blip-image-captioning-large",
    "vit_gpt2": "nlpconnect_vit-gpt2-image-captioning",
    "blip2_2_7b": "Salesforce_blip2-opt-2.7b",
    "blip2_6_7b": "Salesforce_blip2-opt-6.7b",
}

# 旧 CLI / 脚本 id → 新 id（解析时统一，JSON 输出为新 id）
_LEGACY_MODEL_ALIASES: dict[str, str] = {
    "fast": "blip_base",
    "balanced": "blip_large",
    "detailed": "vit_gpt2",
    "photo": "blip2_2_7b",
    "git_large": "blip2_6_7b",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def vendor_hf_root() -> Path:
    override = os.environ.get("PHOTO_ANALYZER_HF_VENDOR_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _repo_root() / "models" / "hf"


def local_model_dir_for_spec(spec: CaptionModelSpec) -> Path:
    return vendor_hf_root() / VENDOR_DIR_NAMES[spec.key]


MODEL_SPECS = {
    "blip_base": CaptionModelSpec(
        key="blip_base",
        label="BLIP-B（快）",
        model_id="Salesforce/blip-image-captioning-base",
        capability="主体识别基础稳定，适合快速初筛。",
        speed="CPU 下通常 2-4 秒/张。",
    ),
    "blip_large": CaptionModelSpec(
        key="blip_large",
        label="BLIP-L（较快）",
        model_id="Salesforce/blip-image-captioning-large",
        capability="主体和场景判断更稳，适合作为默认模型。",
        speed="CPU 下通常 3-8 秒/张。",
    ),
    "vit_gpt2": CaptionModelSpec(
        key="vit_gpt2",
        label="ViT-GPT2（中）",
        model_id="nlpconnect/vit-gpt2-image-captioning",
        capability="描述更开放，细节词更多，但偶尔会更发散。",
        speed="CPU 下通常 4-9 秒/张。",
    ),
    "blip2_2_7b": CaptionModelSpec(
        key="blip2_2_7b",
        label="BLIP-2 2.7B（慢）",
        model_id="Salesforce/blip2-opt-2.7b",
        capability="BLIP-2（OPT 2.7B），比传统 BLIP 更强，适合作为高质量补充；默认仍建议优先用 BLIP-L。",
        speed="CPU 下通常 8-25 秒/张，下载与显存/内存占用明显高于 BLIP-L。",
        max_new_tokens=64,
    ),
    "blip2_6_7b": CaptionModelSpec(
        key="blip2_6_7b",
        label="BLIP-2 6.7B（超慢）",
        model_id="Salesforce/blip2-opt-6.7b",
        capability="BLIP-2（OPT 6.7B），能力上限更高但更慢、更大；默认仍建议 BLIP-L 作日常默认。",
        speed="CPU 下通常 15-60 秒/张，首次下载体积大，建议 GPU。",
        max_new_tokens=64,
    ),
}
DEFAULT_MODEL_KEY = "blip_large"

# CLI --model 允许新 id 与旧 id（旧 id 仍会被规范为新 id 再解析）
CLI_MODEL_CHOICES: tuple[str, ...] = tuple(sorted(set(MODEL_SPECS) | set(_LEGACY_MODEL_ALIASES)))


class CaptioningError(RuntimeError):
    """Raised when local image captioning cannot run."""


def available_caption_models() -> list[CaptionModelSpec]:
    return [
        MODEL_SPECS[k]
        for k in ("blip_base", "blip_large", "vit_gpt2", "blip2_2_7b", "blip2_6_7b")
    ]


def normalize_model_key(model_key: str | None) -> str:
    raw = (model_key or DEFAULT_MODEL_KEY).strip().lower()
    return _LEGACY_MODEL_ALIASES.get(raw, raw)


def resolve_model_spec(model_key: str | None) -> CaptionModelSpec:
    key = normalize_model_key(model_key)
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


def resolve_local_vendor_model_path(
    spec: CaptionModelSpec,
    progress_callback: ProgressCallback | None = None,
) -> str:
    """仅使用项目（或 PHOTO_ANALYZER_HF_VENDOR_ROOT）下已存在的快照，不发起下载。"""
    d = local_model_dir_for_spec(spec)
    cfg = d / "config.json"
    if not cfg.is_file():
        raise CaptioningError(
            "本地模型未就绪：缺少 "
            f"{cfg}。请在项目根执行：python3 scripts/vend_hf_models.py（默认使用 hf-mirror.com）"
        )
    _emit_progress(
        progress_callback,
        {"phase": "cache", "status": f"使用本地模型 {d.name}"},
    )
    return str(d.resolve())


def _caption_pipeline(model_key: str, progress_callback: ProgressCallback | None = None):
    if not _dependencies_available():
        raise CaptioningError("本地图像描述模型不可用：缺少 PyTorch 或 transformers，已退回纯规则标签。")

    spec = resolve_model_spec(model_key)
    if spec.key in _PIPELINE_CACHE:
        _LAST_INIT_SECONDS[spec.key] = 0.0
        return _PIPELINE_CACHE[spec.key]

    started_at = time.perf_counter()
    local_path = resolve_local_vendor_model_path(spec, progress_callback)
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
            output = captioner(rgb, max_new_tokens=spec.max_new_tokens)
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
