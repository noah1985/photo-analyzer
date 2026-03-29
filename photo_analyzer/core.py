from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError

from .captioning import CaptioningError, generate_caption


ANALYSIS_VERSION = "1.0.0"
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "GIF", "TIFF"}
VALID_TAG_GROUPS = {"subject", "scene", "style"}


class AnalysisError(Exception):
    """Raised when an image cannot be analyzed."""


class TaxonomyError(AnalysisError):
    """Raised when taxonomy configuration is invalid."""


@dataclass
class ImageInfo:
    path: str
    format: str
    width: int
    height: int
    orientation: str
    aspect_ratio: float


@dataclass
class ImageMetrics:
    brightness: float
    contrast: float
    saturation: float
    temperature: str
    sharpness: float


@dataclass
class TagDefinition:
    id: str
    label: str
    group: str
    enabled: bool
    trigger_terms: List[str]
    metric_rules: Dict[str, object]
    summary_priority: int


@dataclass
class AnalysisResult:
    image: ImageInfo
    metrics: ImageMetrics
    caption: str
    tags: List[str]
    summary: str
    analysis_version: str
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def taxonomy_path() -> Path:
    return Path(__file__).resolve().parent / "taxonomy.json"


def load_taxonomy() -> List[TagDefinition]:
    path = taxonomy_path()
    if not path.exists():
        raise TaxonomyError(f"标签配置不存在：{path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TaxonomyError(f"标签配置不是合法 JSON：{path}") from exc

    categories = payload.get("categories")
    if not isinstance(categories, dict):
        raise TaxonomyError("标签配置缺少 categories 对象")

    definitions: List[TagDefinition] = []
    for group_name in ("subject", "scene", "style"):
        entries = categories.get(group_name)
        if not isinstance(entries, list):
            raise TaxonomyError(f"标签配置缺少 categories.{group_name} 列表")
        for entry in entries:
            if not isinstance(entry, dict):
                raise TaxonomyError(f"标签配置 categories.{group_name} 中存在非法项")
            required = ("id", "label", "group", "enabled", "trigger_terms", "metric_rules", "summary_priority")
            missing = [key for key in required if key not in entry]
            if missing:
                raise TaxonomyError(
                    f"标签配置项缺少字段：{', '.join(missing)}"
                )
            group = str(entry["group"])
            if group not in VALID_TAG_GROUPS:
                raise TaxonomyError(f"标签配置项 group 非法：{group}")
            trigger_terms = entry["trigger_terms"]
            metric_rules = entry["metric_rules"]
            if not isinstance(trigger_terms, list) or not isinstance(metric_rules, dict):
                raise TaxonomyError(f"标签配置项格式非法：{entry.get('id', '<unknown>')}")
            definitions.append(
                TagDefinition(
                    id=str(entry["id"]),
                    label=str(entry["label"]),
                    group=group,
                    enabled=bool(entry["enabled"]),
                    trigger_terms=[str(term).lower() for term in trigger_terms],
                    metric_rules=metric_rules,
                    summary_priority=int(entry["summary_priority"]),
                )
            )
    return definitions


def _orientation(width: int, height: int) -> str:
    if width > height:
        return "横图"
    if height > width:
        return "竖图"
    return "方图"


def _compute_metrics(image: Image.Image) -> ImageMetrics:
    rgb = image.convert("RGB")
    stat = ImageStat.Stat(rgb)
    grayscale = rgb.convert("L")
    grayscale_stat = ImageStat.Stat(grayscale)
    edge_stat = ImageStat.Stat(grayscale.filter(ImageFilter.FIND_EDGES))

    brightness = grayscale_stat.mean[0] / 255 * 100
    contrast = grayscale_stat.stddev[0] / 255 * 100

    resized = rgb.resize((min(rgb.width, 160), min(rgb.height, 160)))
    pixels = list(resized.getdata())
    saturation_sum = 0.0
    for r, g, b in pixels:
        maximum = max(r, g, b)
        minimum = min(r, g, b)
        saturation_sum += 0.0 if maximum == 0 else (maximum - minimum) / maximum
    saturation = (saturation_sum / max(1, len(pixels))) * 100

    mean_r, _mean_g, mean_b = stat.mean
    if mean_r - mean_b > 12:
        temperature = "偏暖"
    elif mean_b - mean_r > 12:
        temperature = "偏冷"
    else:
        temperature = "中性"

    sharpness = edge_stat.mean[0] / 255 * 100

    return ImageMetrics(
        brightness=round(brightness, 1),
        contrast=round(contrast, 1),
        saturation=round(saturation, 1),
        temperature=temperature,
        sharpness=round(sharpness, 1),
    )


def _metric_value(metrics: ImageMetrics, aspect_ratio: float, metric_name: str) -> float | str:
    mapping: Dict[str, float | str] = {
        "brightness": metrics.brightness,
        "contrast": metrics.contrast,
        "saturation": metrics.saturation,
        "temperature": metrics.temperature,
        "sharpness": metrics.sharpness,
        "aspect_ratio": aspect_ratio,
    }
    return mapping[metric_name]


def _match_trigger_terms(caption: str, definition: TagDefinition) -> bool:
    text = caption.lower()
    if not text or not definition.trigger_terms:
        return False
    return any(term in text for term in definition.trigger_terms)


def _match_metric_rules(metrics: ImageMetrics, aspect_ratio: float, definition: TagDefinition) -> bool:
    rules = definition.metric_rules
    if not rules:
        return False

    if "temperature" in rules and metrics.temperature != str(rules["temperature"]):
        return False

    comparisons = {
        "brightness_lt": lambda value, threshold: float(value) < float(threshold),
        "brightness_gt": lambda value, threshold: float(value) > float(threshold),
        "contrast_lt": lambda value, threshold: float(value) < float(threshold),
        "contrast_gt": lambda value, threshold: float(value) > float(threshold),
        "saturation_lt": lambda value, threshold: float(value) < float(threshold),
        "saturation_gt": lambda value, threshold: float(value) > float(threshold),
        "sharpness_lt": lambda value, threshold: float(value) < float(threshold),
        "sharpness_gt": lambda value, threshold: float(value) > float(threshold),
        "aspect_ratio_lt": lambda value, threshold: float(value) < float(threshold),
        "aspect_ratio_gt": lambda value, threshold: float(value) > float(threshold),
    }

    metric_name_map = {
        "brightness_lt": "brightness",
        "brightness_gt": "brightness",
        "contrast_lt": "contrast",
        "contrast_gt": "contrast",
        "saturation_lt": "saturation",
        "saturation_gt": "saturation",
        "sharpness_lt": "sharpness",
        "sharpness_gt": "sharpness",
        "aspect_ratio_lt": "aspect_ratio",
        "aspect_ratio_gt": "aspect_ratio",
    }

    for rule_name, threshold in rules.items():
        if rule_name == "temperature":
            continue
        if rule_name not in comparisons:
            raise TaxonomyError(f"标签配置包含未知 metric_rules：{rule_name}")
        value = _metric_value(metrics, aspect_ratio, metric_name_map[rule_name])
        if not comparisons[rule_name](value, threshold):
            return False
    return True


def _select_tags(
    caption: str,
    metrics: ImageMetrics,
    aspect_ratio: float,
    definitions: List[TagDefinition],
) -> List[TagDefinition]:
    matched: List[TagDefinition] = []
    for definition in definitions:
        if not definition.enabled:
            continue
        if _match_trigger_terms(caption, definition) or _match_metric_rules(metrics, aspect_ratio, definition):
            matched.append(definition)

    matched.sort(key=lambda item: (item.summary_priority, item.label))
    return matched


def _build_summary(orientation: str, caption: str, tags: List[TagDefinition]) -> str:
    if not tags:
        if caption:
            return f"这是一张{orientation}，模型描述接近“{caption}”。"
        return f"这是一张{orientation}。"

    grouped = {
        "subject": [item.label for item in tags if item.group == "subject"],
        "scene": [item.label for item in tags if item.group == "scene"],
        "style": [item.label for item in tags if item.group == "style"],
    }
    selected: List[str] = []
    for group_name in ("subject", "scene", "style"):
        selected.extend(grouped[group_name][:2 if group_name == "style" else 1])

    if caption:
        return f"这是一张{orientation}，模型描述接近“{caption}”，整体特征包括：{'、'.join(selected)}。"
    return f"这是一张{orientation}，当前可识别的特征包括：{'、'.join(selected)}。"


def analyze_image(image_path: str) -> AnalysisResult:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise AnalysisError(f"文件不存在：{path}")
    if not path.is_file():
        raise AnalysisError(f"不是文件：{path}")

    try:
        definitions = load_taxonomy()
    except TaxonomyError:
        raise

    try:
        with Image.open(path) as image:
            image_format = (image.format or "UNKNOWN").upper()
            if image_format not in SUPPORTED_FORMATS:
                raise AnalysisError(f"不支持的图片格式：{image_format}")
            width, height = image.size
            orientation = _orientation(width, height)
            aspect_ratio = round(width / height, 2) if height else 0.0
            metrics = _compute_metrics(image)
    except UnidentifiedImageError as exc:
        raise AnalysisError(f"无法识别为图片文件：{path}") from exc
    except OSError as exc:
        raise AnalysisError(f"读取图片失败：{path}") from exc

    image_info = ImageInfo(
        path=str(path),
        format=image_format,
        width=width,
        height=height,
        orientation=orientation,
        aspect_ratio=aspect_ratio,
    )

    errors: List[str] = []
    caption = ""
    try:
        caption = generate_caption(str(path))
    except (CaptioningError, RuntimeError) as exc:
        errors.append(str(exc))

    tag_defs = _select_tags(caption, metrics, aspect_ratio, definitions)
    tags = [item.label for item in tag_defs]
    summary = _build_summary(orientation, caption, tag_defs)

    return AnalysisResult(
        image=image_info,
        metrics=metrics,
        caption=caption,
        tags=tags,
        summary=summary,
        analysis_version=ANALYSIS_VERSION,
        errors=errors,
    )
