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


ANALYSIS_VERSION = "1.2.4"
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "GIF", "TIFF"}
TAG_GROUP_ORDER = (
    "subject_content",
    "scene_lighting",
    "composition_distance",
    "style_impression",
)
TAG_GROUP_LABELS: Dict[str, str] = {
    "subject_content": "题材 / 内容",
    "scene_lighting": "场景 / 光线",
    "composition_distance": "构图 / 景别",
    "style_impression": "色调倾向",
}
VALID_TAG_GROUPS = set(TAG_GROUP_ORDER)


class AnalysisError(Exception):
    """Raised when an image cannot be analyzed."""


class TaxonomyError(AnalysisError):
    """Raised when taxonomy configuration is invalid."""


# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------


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
class Signals:
    """Layer-1 output: raw observations extracted from image + caption."""
    caption: str
    tokens: frozenset[str]
    normalized_text: str
    metrics: ImageMetrics
    aspect_ratio: float


@dataclass
class TagRule:
    type: str
    score: float
    tokens: List[str] = field(default_factory=list)
    phrases: List[str] = field(default_factory=list)
    field_name: str = ""
    value: object = None


@dataclass
class TagDefinition:
    id: str
    label: str
    group: str
    enabled: bool
    rules: List[TagRule]
    conflicts: List[str]


@dataclass
class GroupDefinition:
    name: str
    label: str
    max_tags: int


@dataclass
class Taxonomy:
    version: int
    groups: List[GroupDefinition]
    tags: List[TagDefinition]

    def group_labels(self) -> Dict[str, str]:
        return {g.name: g.label for g in self.groups}

    def group_max_tags(self) -> Dict[str, int]:
        return {g.name: g.max_tags for g in self.groups}

    def enabled_labels_by_group(self) -> Dict[str, set[str]]:
        result: Dict[str, set[str]] = {g.name: set() for g in self.groups}
        for tag in self.tags:
            if tag.enabled:
                result[tag.group].add(tag.label)
        return result


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


# ---------------------------------------------------------------------------
#  Taxonomy loading (v2)
# ---------------------------------------------------------------------------

_RULE_TYPES = frozenset({"token_any", "phrase_any", "metric_lt", "metric_gt", "metric_eq"})


def taxonomy_path() -> Path:
    return Path(__file__).resolve().parent / "taxonomy.json"


def _parse_rule(raw: dict) -> TagRule:
    rtype = str(raw.get("type", ""))
    if rtype not in _RULE_TYPES:
        raise TaxonomyError(f"未知规则类型：{rtype}")
    return TagRule(
        type=rtype,
        score=float(raw.get("score", 0)),
        tokens=[str(t).lower() for t in raw.get("tokens", [])],
        phrases=[str(p).lower() for p in raw.get("phrases", [])],
        field_name=str(raw.get("field", "")),
        value=raw.get("value"),
    )


def load_taxonomy() -> Taxonomy:
    path = taxonomy_path()
    if not path.exists():
        raise TaxonomyError(f"标签配置不存在：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TaxonomyError(f"标签配置不是合法 JSON：{path}") from exc

    version = int(payload.get("version", 1))

    raw_groups = payload.get("groups")
    if not isinstance(raw_groups, dict):
        raise TaxonomyError("标签配置缺少 groups 对象")
    groups: List[GroupDefinition] = []
    for group_name in TAG_GROUP_ORDER:
        g = raw_groups.get(group_name)
        if not isinstance(g, dict):
            raise TaxonomyError(f"标签配置缺少 groups.{group_name}")
        groups.append(GroupDefinition(
            name=group_name,
            label=str(g.get("label", group_name)),
            max_tags=int(g.get("max_tags", 2)),
        ))

    raw_tags = payload.get("tags")
    if not isinstance(raw_tags, list):
        raise TaxonomyError("标签配置缺少 tags 列表")
    tags: List[TagDefinition] = []
    for entry in raw_tags:
        if not isinstance(entry, dict):
            raise TaxonomyError("标签配置 tags 列表中存在非法项")
        group = str(entry.get("group", ""))
        if group not in VALID_TAG_GROUPS:
            raise TaxonomyError(f"标签配置项 group 非法：{group}")
        raw_rules = entry.get("rules", [])
        if not isinstance(raw_rules, list):
            raise TaxonomyError(f"标签配置项 rules 格式非法：{entry.get('id')}")
        parsed_rules = [_parse_rule(r) for r in raw_rules]
        tags.append(TagDefinition(
            id=str(entry["id"]),
            label=str(entry["label"]),
            group=group,
            enabled=bool(entry.get("enabled", True)),
            rules=parsed_rules,
            conflicts=[str(c) for c in entry.get("conflicts", [])],
        ))

    taxonomy = Taxonomy(version=version, groups=groups, tags=tags)

    global TAG_GROUP_LABELS  # noqa: PLW0603
    TAG_GROUP_LABELS.update(taxonomy.group_labels())

    return taxonomy


# ---------------------------------------------------------------------------
#  Layer 1: Signal extraction
# ---------------------------------------------------------------------------


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


def extract_signals(caption: str, metrics: ImageMetrics, aspect_ratio: float) -> Signals:
    normalized = re.sub(r"[^a-z0-9]+", " ", caption.lower()).strip()
    tokens = frozenset(normalized.split()) if normalized else frozenset()
    return Signals(
        caption=caption,
        tokens=tokens,
        normalized_text=normalized,
        metrics=metrics,
        aspect_ratio=aspect_ratio,
    )


# ---------------------------------------------------------------------------
#  Layer 2: Tag scoring
# ---------------------------------------------------------------------------


def _eval_token_any(rule: TagRule, signals: Signals) -> float:
    for token in rule.tokens:
        if token in signals.tokens:
            return rule.score
    return 0.0


def _eval_phrase_any(rule: TagRule, signals: Signals) -> float:
    padded = f" {signals.normalized_text} "
    for phrase in rule.phrases:
        normalized_phrase = re.sub(r"[^a-z0-9]+", " ", phrase).strip()
        if f" {normalized_phrase} " in padded:
            return rule.score
    return 0.0


def _metric_value(metrics: ImageMetrics, aspect_ratio: float, field_name: str) -> float | str:
    mapping: Dict[str, float | str] = {
        "brightness": metrics.brightness,
        "contrast": metrics.contrast,
        "saturation": metrics.saturation,
        "temperature": metrics.temperature,
        "sharpness": metrics.sharpness,
        "aspect_ratio": aspect_ratio,
    }
    if field_name not in mapping:
        raise TaxonomyError(f"未知 metric 字段：{field_name}")
    return mapping[field_name]


def _eval_metric_lt(rule: TagRule, signals: Signals) -> float:
    val = _metric_value(signals.metrics, signals.aspect_ratio, rule.field_name)
    if isinstance(val, (int, float)) and val < float(rule.value):
        return rule.score
    return 0.0


def _eval_metric_gt(rule: TagRule, signals: Signals) -> float:
    val = _metric_value(signals.metrics, signals.aspect_ratio, rule.field_name)
    if isinstance(val, (int, float)) and val > float(rule.value):
        return rule.score
    return 0.0


def _eval_metric_eq(rule: TagRule, signals: Signals) -> float:
    val = _metric_value(signals.metrics, signals.aspect_ratio, rule.field_name)
    if str(val) == str(rule.value):
        return rule.score
    return 0.0


_RULE_EVALUATORS = {
    "token_any":  _eval_token_any,
    "phrase_any": _eval_phrase_any,
    "metric_lt":  _eval_metric_lt,
    "metric_gt":  _eval_metric_gt,
    "metric_eq":  _eval_metric_eq,
}


def score_tag(definition: TagDefinition, signals: Signals) -> float:
    """Sum the scores from all matching rules of a tag definition."""
    total = 0.0
    for rule in definition.rules:
        evaluator = _RULE_EVALUATORS.get(rule.type)
        if evaluator:
            total += evaluator(rule, signals)
    return total


def score_all_tags(taxonomy: Taxonomy, signals: Signals) -> Dict[str, float]:
    """Return {tag_label: total_score} for every enabled tag."""
    scores: Dict[str, float] = {}
    for tag in taxonomy.tags:
        if not tag.enabled:
            continue
        s = score_tag(tag, signals)
        if s > 0:
            scores[tag.label] = s
    return scores


# ---------------------------------------------------------------------------
#  Layer 3: Tag selection (score → conflict resolution → top-K)
# ---------------------------------------------------------------------------


def _build_conflict_map(taxonomy: Taxonomy) -> Dict[str, frozenset[str]]:
    """Build label→conflicting_labels from taxonomy declarations."""
    cmap: Dict[str, set[str]] = {}
    for tag in taxonomy.tags:
        if tag.conflicts:
            cmap.setdefault(tag.label, set()).update(tag.conflicts)
    return {label: frozenset(conflicts) for label, conflicts in cmap.items()}


def select_tags(
    scores: Dict[str, float],
    taxonomy: Taxonomy,
) -> Dict[str, List[str]]:
    """Pick top scoring tags per group, respecting conflicts and max_tags."""
    conflict_map = _build_conflict_map(taxonomy)
    max_tags = taxonomy.group_max_tags()

    grouped: Dict[str, List[tuple[float, str]]] = {g.name: [] for g in taxonomy.groups}
    for tag in taxonomy.tags:
        if not tag.enabled:
            continue
        s = scores.get(tag.label, 0.0)
        if s > 0:
            grouped[tag.group].append((s, tag.label))

    result: Dict[str, List[str]] = {}
    for group_name in TAG_GROUP_ORDER:
        candidates = sorted(grouped.get(group_name, []), key=lambda x: -x[0])
        selected: List[str] = []
        banned: set[str] = set()
        limit = max_tags.get(group_name, 2)
        for _score, label in candidates:
            if label in banned:
                continue
            selected.append(label)
            banned |= conflict_map.get(label, frozenset())
            if len(selected) >= limit:
                break
        result[group_name] = selected
    return result


# ---------------------------------------------------------------------------
#  Summary builder
# ---------------------------------------------------------------------------


def _build_summary(
    orientation: str,
    caption: str,
    tag_groups: Dict[str, List[str]],
) -> str:
    subject = tag_groups.get("subject_content", [])
    scene = tag_groups.get("scene_lighting", [])
    composition = tag_groups.get("composition_distance", [])
    style = tag_groups.get("style_impression", [])

    parts = [f"这是一张{orientation}"]
    if subject:
        parts.append(f"内容更接近{subject[0]}")
    if scene:
        parts.append(f"拍摄环境偏{scene[0]}")
    if style:
        style_text = "、".join(style[:2])
        parts.append(f"色调呈现{style_text}")
    elif composition:
        parts.append(f"画面带有{composition[0]}")

    sentence = "，".join(parts) + "。"
    if caption:
        return f"{sentence} 模型描述接近\u201c{caption}\u201d。"
    return sentence


def _flatten_tag_groups(tag_groups: Dict[str, List[str]]) -> List[str]:
    tags: List[str] = []
    for group_name in TAG_GROUP_ORDER:
        tags.extend(tag_groups.get(group_name, []))
    return tags


# 仅含 person/someone 而无人脸/群体词时，不把「手+食物/摆盘」类误判为题材人像
_STRONG_PORTRAIT_TOKENS = frozenset(
    {
        "woman",
        "women",
        "man",
        "men",
        "girl",
        "girls",
        "boy",
        "boys",
        "face",
        "faces",
        "portrait",
        "people",
        "couple",
        "couples",
        "bride",
        "groom",
        "selfie",
        "baby",
        "toddler",
        "child",
        "children",
        "friends",
        "ladies",
        "gentleman",
        "gentlemen",
    }
)


def _refine_subject_food_vs_portrait(signals: Signals, tag_groups: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """当题材同时命中人像+食物且描述明显是食物/手部操作时，去掉仅凭 person 命中的人像。"""
    subj = tag_groups.get("subject_content", [])
    if "人像" not in subj or "食物" not in subj:
        return tag_groups
    if signals.tokens & _STRONG_PORTRAIT_TOKENS:
        return tag_groups
    text = signals.normalized_text
    padded = f" {text} " if text else ""
    food_prep = (
        "tweezers" in signals.tokens
        or " decorating " in padded
        or " plating " in padded
        or " garnish " in padded
        or " garnishing " in padded
        or (
            ("hand" in signals.tokens or "hands" in signals.tokens)
            and (
                signals.tokens
                & {
                    "tart",
                    "pastry",
                    "dessert",
                    "cake",
                    "berry",
                    "berries",
                    "raspberry",
                    "blueberry",
                }
            )
        )
    )
    food_focus = bool(
        signals.tokens
        & {
            "tart",
            "pastry",
            "dessert",
            "cake",
            "berry",
            "berries",
            "raspberry",
            "blueberry",
            "fruit",
            "food",
        }
    )
    only_weak_human = bool(signals.tokens & {"person", "someone"})
    if not (food_prep or (food_focus and only_weak_human)):
        return tag_groups
    out = {k: list(v) for k, v in tag_groups.items()}
    out["subject_content"] = [x for x in out["subject_content"] if x != "人像"]
    return out


def _refine_subject_drop_animal_for_figurine(signals: Signals, tag_groups: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """摆件/模型上的动物造型不应标为题材动物。"""
    if "动物" not in tag_groups.get("subject_content", []):
        return tag_groups
    if "figurine" in signals.tokens or "figurines" in signals.tokens:
        out = {k: list(v) for k, v in tag_groups.items()}
        out["subject_content"] = [x for x in out["subject_content"] if x != "动物"]
        return out
    return tag_groups


# ---------------------------------------------------------------------------
#  Public entry point
# ---------------------------------------------------------------------------


def analyze_image(image_path: str, *, model_key: str | None = None) -> AnalysisResult:
    started_at = time.perf_counter()
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise AnalysisError(f"文件不存在：{path}")
    if not path.is_file():
        raise AnalysisError(f"不是文件：{path}")

    taxonomy = load_taxonomy()

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
    try:
        caption = generate_caption(str(path), model_spec.key)
    except (CaptioningError, RuntimeError) as exc:
        errors.append(str(exc))
    finally:
        model_initialization_seconds = consume_last_model_init_seconds(model_spec.key)

    signals = extract_signals(caption, metrics, aspect_ratio)
    scores = score_all_tags(taxonomy, signals)
    tag_groups = select_tags(scores, taxonomy)
    tag_groups = _refine_subject_food_vs_portrait(signals, tag_groups)
    tag_groups = _refine_subject_drop_animal_for_figurine(signals, tag_groups)
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
