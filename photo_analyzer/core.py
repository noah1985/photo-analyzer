from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError

from .captioning import (
    DEFAULT_MODEL_KEY,
    CaptioningError,
    consume_last_model_init_seconds,
    generate_caption,
    resolve_model_spec,
)


ANALYSIS_VERSION = "1.1.0"
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "GIF", "TIFF"}
TAG_GROUP_ORDER = (
    "subject_content",
    "scene_lighting",
    "composition_distance",
    "style_impression",
)
TAG_GROUP_LABELS = {
    "subject_content": "题材 / 内容",
    "scene_lighting": "场景 / 光线",
    "composition_distance": "构图 / 景别",
    "style_impression": "风格 / 观感",
}
VALID_TAG_GROUPS = set(TAG_GROUP_ORDER)


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
    caption_model: str
    caption_model_label: str
    model_initialization_seconds: float
    analysis_duration_seconds: float
    tag_groups: Dict[str, List[str]]
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
    for group_name in TAG_GROUP_ORDER:
        entries = categories.get(group_name)
        if not isinstance(entries, list):
            raise TaxonomyError(f"标签配置缺少 categories.{group_name} 列表")
        for entry in entries:
            if not isinstance(entry, dict):
                raise TaxonomyError(f"标签配置 categories.{group_name} 中存在非法项")
            required = (
                "id",
                "label",
                "group",
                "enabled",
                "trigger_terms",
                "metric_rules",
                "summary_priority",
            )
            missing = [key for key in required if key not in entry]
            if missing:
                raise TaxonomyError(f"标签配置项缺少字段：{', '.join(missing)}")
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
    normalized = re.sub(r"[^a-z0-9]+", " ", text).strip()
    padded = f" {normalized} "
    for term in definition.trigger_terms:
        normalized_term = re.sub(r"[^a-z0-9]+", " ", term.lower()).strip()
        if not normalized_term:
            continue
        if f" {normalized_term} " in padded:
            return True
    return False


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


def _select_tag_groups(
    caption: str,
    metrics: ImageMetrics,
    aspect_ratio: float,
    definitions: List[TagDefinition],
) -> Dict[str, List[str]]:
    grouped_matches: Dict[str, List[tuple[int, int, int, str]]] = {group: [] for group in TAG_GROUP_ORDER}

    for definition in definitions:
        if not definition.enabled:
            continue
        trigger_match = _match_trigger_terms(caption, definition)
        metric_match = _match_metric_rules(metrics, aspect_ratio, definition)
        if not trigger_match and not metric_match:
            continue
        grouped_matches[definition.group].append(
            (
                0 if trigger_match else 1,
                0 if metric_match else 1,
                definition.summary_priority,
                definition.label,
            )
        )

    tag_groups: Dict[str, List[str]] = {group: [] for group in TAG_GROUP_ORDER}
    for group_name in TAG_GROUP_ORDER:
        ranked = sorted(grouped_matches[group_name])
        seen: set[str] = set()
        for _trigger_rank, _metric_rank, _priority, label in ranked:
            if label in seen:
                continue
            seen.add(label)
            tag_groups[group_name].append(label)
            if len(tag_groups[group_name]) == 2:
                break
    return tag_groups


def _flatten_tag_groups(tag_groups: Dict[str, List[str]]) -> List[str]:
    tags: List[str] = []
    for group_name in TAG_GROUP_ORDER:
        tags.extend(tag_groups.get(group_name, []))
    return tags


def _insert_front(values: List[str], label: str) -> List[str]:
    remaining = [item for item in values if item != label]
    return [label, *remaining]


def _remove_labels(values: List[str], labels: set[str]) -> List[str]:
    return [item for item in values if item not in labels]


def _refine_tag_groups(
    caption: str,
    metrics: ImageMetrics,
    orientation: str,
    tag_groups: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    text = re.sub(r"[^a-z0-9]+", " ", caption.lower()).strip()
    tokens = set(text.split())
    padded = f" {text} " if text else ""

    def has_phrase(*phrases: str) -> bool:
        for phrase in phrases:
            normalized = re.sub(r"[^a-z0-9]+", " ", phrase.lower()).strip()
            if normalized and f" {normalized} " in padded:
                return True
        return False

    refined = {group: list(values) for group, values in tag_groups.items()}

    _PERSON_TOKENS = {
        "woman", "man", "girl", "boy", "person", "people", "face", "portrait",
        "women", "men", "girls", "boys", "child", "children", "kid", "kids",
        "baby", "toddler", "player", "singer", "dancer", "couple",
    }
    has_person = bool(tokens & _PERSON_TOKENS) or has_phrase(
        "young girl", "young boy", "old man", "old woman",
        "young woman", "young man", "little girl", "little boy",
    )
    single_person = has_phrase(
        "a woman", "a man", "a girl", "a boy", "a child",
        "single person", "solo portrait", "one person",
    )
    has_flower = bool(tokens & {"flower", "flowers", "blossom", "rose", "tulip"})
    has_drink = bool(tokens & {"coffee", "tea", "wine", "drink", "cup", "glass", "bottle"})
    has_sports = bool(tokens & {"sports", "sport", "runner", "running", "racing", "race", "swimmer", "swimming"})
    has_helmet_action = ("helmet" in tokens) and bool(tokens & {"riding", "kart", "motorcycle", "bike", "cycling"})
    has_indoor_hint = bool(tokens & {"indoors", "indoor", "room", "floor", "mirror", "cabinet", "dresser", "table", "chair"})
    has_black_white = has_phrase("black and white", "monochrome", "grayscale") or metrics.saturation < 8

    has_music = bool(tokens & {"piano", "guitar", "violin", "cello", "drums", "flute", "trumpet", "saxophone"}) or has_phrase(
        "playing music", "playing a song", "musical performance", "musician", "pianist", "guitarist",
    )
    has_performance = has_phrase(
        "performance", "performing", "stage", "concert", "recital", "dancing",
    )
    has_activity = has_music or has_performance or has_sports or has_helmet_action
    is_street_context = bool(tokens & {"street", "sidewalk", "crosswalk"}) or has_phrase(
        "walking down", "walking on", "walking in",
    )
    is_portrait_like = (
        has_phrase("portrait", "posing", "looking at camera", "headshot",
                   "close up of a", "selfie", "self portrait")
        or (single_person and not has_activity)
    )
    _CHILD_TOKENS = {"child", "children", "kid", "kids", "baby", "toddler"}
    is_child = bool(tokens & _CHILD_TOKENS) or has_phrase(
        "young girl", "young boy", "young girls", "young boys",
        "little girl", "little boy", "little girls", "little boys",
    )

    if has_person:
        refined["subject_content"] = _remove_labels(refined["subject_content"], {"野生动物"})
        if not has_drink:
            refined["subject_content"] = _remove_labels(refined["subject_content"], {"饮品"})
        if "camera" in tokens and not has_drink:
            refined["subject_content"] = _remove_labels(refined["subject_content"], {"静物"})

        if has_music:
            refined["subject_content"] = _insert_front(refined["subject_content"], "演奏")
        elif has_performance:
            refined["subject_content"] = _insert_front(refined["subject_content"], "活动现场")
        elif is_street_context and not is_portrait_like:
            refined["subject_content"] = _insert_front(refined["subject_content"], "街拍")
        elif is_portrait_like:
            refined["subject_content"] = _insert_front(refined["subject_content"], "人像")
            if single_person:
                refined["subject_content"] = _insert_front(refined["subject_content"], "单人肖像")

        if is_child:
            refined["subject_content"] = _insert_front(refined["subject_content"], "儿童")

        if not refined["subject_content"]:
            refined["subject_content"].append("人像")

        if has_indoor_hint or has_music:
            refined["scene_lighting"] = _insert_front(refined["scene_lighting"], "室内")
        if has_flower and not single_person:
            refined["subject_content"] = _insert_front(refined["subject_content"], "花卉")

        if is_portrait_like:
            if orientation == "竖图":
                refined["composition_distance"] = _insert_front(refined["composition_distance"], "竖幅构图")
            if bool(tokens & {"face", "eye", "eyes"}) or has_phrase("close up", "close up portrait", "headshot"):
                refined["composition_distance"] = _insert_front(refined["composition_distance"], "特写")
            else:
                refined["composition_distance"] = _insert_front(refined["composition_distance"], "近景")

    if has_sports or has_helmet_action:
        refined["subject_content"] = _insert_front(refined["subject_content"], "运动")
        refined["composition_distance"] = _insert_front(refined["composition_distance"], "动态构图")

    if has_black_white:
        refined["style_impression"] = _insert_front(refined["style_impression"], "黑白倾向")

    for group_name in TAG_GROUP_ORDER:
        refined[group_name] = refined[group_name][:2]

    return refined


def _build_summary(
    orientation: str,
    caption: str,
    tag_groups: Dict[str, List[str]],
) -> str:
    subject = tag_groups["subject_content"]
    scene = tag_groups["scene_lighting"]
    composition = tag_groups["composition_distance"]
    style = tag_groups["style_impression"]

    parts = [f"这是一张{orientation}"]
    if subject:
        parts.append(f"内容更接近{subject[0]}")
    if scene:
        parts.append(f"拍摄环境偏{scene[0]}")
    if style:
        style_text = "、".join(style[:2])
        parts.append(f"整体观感呈现{style_text}")
    elif composition:
        parts.append(f"画面带有{composition[0]}")

    sentence = "，".join(parts) + "。"
    if caption:
        return f"{sentence} 模型描述接近“{caption}”。"
    return sentence


def _labels_for_group(definitions: List[TagDefinition], group_name: str) -> list[str]:
    return [definition.label for definition in definitions if definition.group == group_name and definition.enabled]


def analyze_image(image_path: str, *, model_key: str | None = None) -> AnalysisResult:
    started_at = time.perf_counter()
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise AnalysisError(f"文件不存在：{path}")
    if not path.is_file():
        raise AnalysisError(f"不是文件：{path}")

    definitions = load_taxonomy()

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

    model_spec = resolve_model_spec(model_key or DEFAULT_MODEL_KEY)

    errors: List[str] = []
    caption = ""
    model_initialization_seconds = 0.0
    tag_groups = {group: [] for group in TAG_GROUP_ORDER}
    try:
        caption = generate_caption(str(path), model_spec.key)
        tag_groups = _select_tag_groups(caption, metrics, aspect_ratio, definitions)
    except (CaptioningError, RuntimeError) as exc:
        errors.append(str(exc))
        tag_groups = _select_tag_groups(caption, metrics, aspect_ratio, definitions)
    finally:
        model_initialization_seconds = consume_last_model_init_seconds(model_spec.key)

    metric_tag_groups = _select_tag_groups("", metrics, aspect_ratio, definitions)
    for group_name in TAG_GROUP_ORDER:
        for label in metric_tag_groups[group_name]:
            if label not in tag_groups[group_name]:
                tag_groups[group_name].append(label)
    tag_groups = _refine_tag_groups(caption, metrics, orientation, tag_groups)
    tags = _flatten_tag_groups(tag_groups)
    summary = _build_summary(orientation, caption, tag_groups)

    return AnalysisResult(
        image=image_info,
        metrics=metrics,
        caption=caption,
        caption_model=model_spec.key,
        caption_model_label=model_spec.label,
        model_initialization_seconds=model_initialization_seconds,
        analysis_duration_seconds=round(max(time.perf_counter() - started_at - model_initialization_seconds, 0.0), 2),
        tag_groups=tag_groups,
        tags=tags,
        summary=summary,
        analysis_version=ANALYSIS_VERSION,
        errors=errors,
    )
