import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from photo_analyzer.captioning import (
    MODEL_SPECS,
    CaptioningError,
    available_caption_models,
    resolve_local_vendor_model_path,
)
from photo_analyzer.cli import build_gallery_item, format_result
from photo_analyzer.core import (
    ANALYSIS_VERSION,
    TAG_GROUP_ORDER,
    AnalysisError,
    AnalysisResult,
    ImageInfo,
    ImageMetrics,
    Signals,
    Taxonomy,
    _refine_subject_food_vs_portrait,
    analyze_image,
    extract_signals,
    load_taxonomy,
    score_all_tags,
    select_tags,
    taxonomy_path,
)
from photo_analyzer.desktop_app import MAX_SAMPLE_COUNT, build_card_tags, clamp_sample_count


TEST_ENV = {"PHOTO_ANALYZER_CAPTION_OVERRIDE": "a warm portrait photo indoors"}


ALLOWED_TAXONOMY_LABELS = frozenset(
    {
        "人像",
        "建筑",
        "风光",
        "食物",
        "动物",
        "运动",
        "微距",
        "室内",
        "室外",
        "夜景",
        "日落",
        "低光",
        "逆光",
        "特写",
        "近景",
        "宽景",
        "对称",
        "主体突出",
        "暖色调",
        "冷色调",
        "黑白",
        "高对比",
        "低对比",
        "高饱和",
        "低饱和",
        "明亮",
    }
)


class PhotoAnalyzerTests(unittest.TestCase):

    # ------------------------------------------------------------------
    #  Layer-2 / Layer-3 unit tests (scoring + selection)
    # ------------------------------------------------------------------

    def _quick_signals(self, caption: str, **metric_overrides: object) -> Signals:
        defaults = dict(brightness=50.0, contrast=12.0, saturation=30.0, temperature="中性", sharpness=10.0)
        defaults.update(metric_overrides)
        metrics = ImageMetrics(**defaults)
        return extract_signals(caption, metrics, aspect_ratio=1.0)

    def test_score_portrait_token(self) -> None:
        taxonomy = load_taxonomy()
        signals = self._quick_signals("a woman standing in a garden")
        scores = score_all_tags(taxonomy, signals)
        self.assertGreater(scores.get("人像", 0), 0)

    def test_score_animal_dog_token(self) -> None:
        taxonomy = load_taxonomy()
        signals = self._quick_signals("a dog laying on the grass")
        scores = score_all_tags(taxonomy, signals)
        self.assertGreater(scores.get("动物", 0), 0)

    def test_conflict_resolution_indoor_outdoor(self) -> None:
        taxonomy = load_taxonomy()
        scores = {"室内": 1.0, "室外": 0.8}
        tag_groups = select_tags(scores, taxonomy)
        scene = tag_groups["scene_lighting"]
        self.assertIn("室内", scene)
        self.assertNotIn("室外", scene)

    def test_conflict_resolution_composition(self) -> None:
        taxonomy = load_taxonomy()
        scores = {"特写": 1.0, "近景": 0.9, "对称": 0.5}
        tag_groups = select_tags(scores, taxonomy)
        comp = tag_groups["composition_distance"]
        self.assertIn("特写", comp)
        self.assertNotIn("近景", comp)
        self.assertIn("对称", comp)

    def test_conflict_resolution_warm_cool(self) -> None:
        taxonomy = load_taxonomy()
        scores = {"暖色调": 1.0, "冷色调": 0.8, "明亮": 0.5}
        tag_groups = select_tags(scores, taxonomy)
        style = tag_groups["style_impression"]
        self.assertIn("暖色调", style)
        self.assertNotIn("冷色调", style)

    def test_conflict_bw_excludes_saturation_tags(self) -> None:
        taxonomy = load_taxonomy()
        scores = {"黑白": 1.5, "高饱和": 0.5}
        tag_groups = select_tags(scores, taxonomy)
        style = tag_groups["style_impression"]
        self.assertIn("黑白", style)
        self.assertNotIn("高饱和", style)

    def test_max_tags_per_group(self) -> None:
        taxonomy = load_taxonomy()
        scores = {"人像": 1.0, "建筑": 0.9, "风光": 0.8, "食物": 0.7}
        tag_groups = select_tags(scores, taxonomy)
        self.assertLessEqual(len(tag_groups["subject_content"]), 2)

    def test_women_plural_triggers_portrait_score(self) -> None:
        taxonomy = load_taxonomy()
        signals = self._quick_signals("two women holding up a lighted object")
        scores = score_all_tags(taxonomy, signals)
        self.assertGreater(scores.get("人像", 0), 0)

    def test_refine_drops_portrait_for_weak_person_plus_food(self) -> None:
        taxonomy = load_taxonomy()
        signals = self._quick_signals("a person is cutting a fruit tart with a knife")
        scores = score_all_tags(taxonomy, signals)
        tag_groups = select_tags(scores, taxonomy)
        refined = _refine_subject_food_vs_portrait(signals, tag_groups)
        self.assertNotIn("人像", refined["subject_content"])
        self.assertIn("食物", refined["subject_content"])

    def test_refine_keeps_portrait_when_woman_and_food(self) -> None:
        taxonomy = load_taxonomy()
        signals = self._quick_signals("a woman decorating a fruit tart in a kitchen")
        scores = score_all_tags(taxonomy, signals)
        tag_groups = select_tags(scores, taxonomy)
        refined = _refine_subject_food_vs_portrait(signals, tag_groups)
        self.assertIn("人像", refined["subject_content"])

    # ------------------------------------------------------------------
    #  Integration tests (full pipeline via analyze_image)
    # ------------------------------------------------------------------

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a colorful bird perched on a branch in the forest",
    )
    def test_bird_caption_maps_to_animal(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (100, 100), (40, 80, 40)).save(path)
            result = analyze_image(str(path))
        self.assertIn("动物", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a macro close up of a butterfly resting on a leaf",
    )
    def test_macro_butterfly_emits_animal_and_macro_composition(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (100, 100), (50, 70, 40)).save(path)
            result = analyze_image(str(path))
        self.assertIn("动物", result.tag_groups["subject_content"])
        self.assertIn("微距", result.tag_groups["composition_distance"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a dog laying on the grass",
    )
    def test_dog_caption_maps_to_pet(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (100, 100), (90, 90, 90)).save(path)
            result = analyze_image(str(path))
        self.assertIn("动物", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="there are two people standing in front of a building with columns",
    )
    def test_two_people_maps_to_portrait_subject(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (90, 140), (110, 105, 95)).save(path)
            result = analyze_image(str(path))
        self.assertIn("人像", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a close up of two red roses on a stem",
    )
    def test_roses_map_to_landscape_and_resolves_close_focus(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (100, 100), (90, 40, 50)).save(path)
            result = analyze_image(str(path))
        self.assertIn("风光", result.tag_groups["subject_content"])
        comp = set(result.tag_groups["composition_distance"])
        self.assertFalse(comp >= {"特写", "近景"})

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a man pushing a cart with a bunch of stuff on it",
    )
    def test_man_with_cart_maps_to_portrait(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (90, 140), (110, 105, 95)).save(path)
            result = analyze_image(str(path))
        self.assertIn("人像", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a woman holding a baby in a stroller",
    )
    def test_mixed_adult_baby_maps_to_portrait(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (90, 140), (110, 105, 95)).save(path)
            result = analyze_image(str(path))
        self.assertIn("人像", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a city skyline with a bridge",
    )
    def test_city_skyline_with_bridge_maps_to_architecture(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (200, 120), (80, 90, 110)).save(path)
            result = analyze_image(str(path))
        self.assertIn("建筑", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a bridge over a body of water",
    )
    def test_bridge_over_water_maps_to_architecture(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (200, 120), (80, 90, 110)).save(path)
            result = analyze_image(str(path))
        self.assertIn("建筑", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="two people in go kart racing gear on a track",
    )
    def test_go_kart_maps_to_sports(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (200, 120), (80, 90, 70)).save(path)
            result = analyze_image(str(path))
        self.assertIn("运动", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a black and white portrait of a woman",
    )
    def test_black_and_white_portrait_gets_bw_style(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (200, 120), (90, 90, 90)).save(path)
            result = analyze_image(str(path))
        self.assertIn("黑白", result.tag_groups["style_impression"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a tall glass sculpture with a lot of lights",
    )
    def test_glass_sculpture_no_allowed_subject_stays_empty(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (90, 140), (40, 40, 60)).save(path)
            result = analyze_image(str(path))
        self.assertEqual(result.tag_groups["subject_content"], [])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a red and gold chinese new year decoration",
    )
    def test_chinese_new_year_tags_stay_in_allowed_vocabulary(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (80, 80), (180, 40, 40)).save(path)
            result = analyze_image(str(path))
        self.assertTrue(set(result.tags) <= ALLOWED_TAXONOMY_LABELS)

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a wooden walkway leads to a grassy field",
    )
    def test_walkway_to_field_maps_to_landscape(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (200, 100), (60, 90, 50)).save(path)
            result = analyze_image(str(path))
        self.assertIn("风光", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="there are many cow figurines on display in a glass case",
    )
    def test_figurine_caption_does_not_emit_pet(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (80, 80), (60, 55, 50)).save(path)
            result = analyze_image(str(path))
        self.assertNotIn("动物", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="there is a plate of food with meat and vegetables on it",
    )
    def test_food_plate_maps_to_food(self, _mock: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (200, 120), (140, 100, 80)).save(path)
            result = analyze_image(str(path))
        self.assertIn("食物", result.tag_groups["subject_content"])

    # ------------------------------------------------------------------
    #  Taxonomy structure tests
    # ------------------------------------------------------------------

    def test_taxonomy_loads_four_groups(self) -> None:
        taxonomy = load_taxonomy()
        self.assertEqual(taxonomy.version, 2)
        self.assertEqual(len(taxonomy.groups), 4)
        self.assertEqual({g.name for g in taxonomy.groups}, set(TAG_GROUP_ORDER))
        self.assertEqual(len(taxonomy.tags), 26)
        labels = {t.label for t in taxonomy.tags}
        self.assertIn("人像", labels)
        self.assertIn("夜景", labels)
        self.assertIn("黑白", labels)
        self.assertTrue(labels <= ALLOWED_TAXONOMY_LABELS)

    def test_all_taxonomy_tags_belong_to_valid_groups(self) -> None:
        taxonomy = load_taxonomy()
        valid_groups = {g.name for g in taxonomy.groups}
        for tag in taxonomy.tags:
            self.assertIn(tag.group, valid_groups, f"Tag {tag.label} has invalid group {tag.group}")

    def test_taxonomy_conflicts_reference_existing_labels(self) -> None:
        taxonomy = load_taxonomy()
        all_labels = {t.label for t in taxonomy.tags}
        for tag in taxonomy.tags:
            for conflict_label in tag.conflicts:
                self.assertIn(
                    conflict_label,
                    all_labels,
                    f"{tag.label} declares conflict with unknown label {conflict_label}",
                )

    # ------------------------------------------------------------------
    #  Captioning / model tests
    # ------------------------------------------------------------------

    def test_photo_model_preset_exists(self) -> None:
        keys = [item.key for item in available_caption_models()]
        self.assertIn("photo", keys)
        self.assertIn("git_large", keys)

    def test_local_vendor_model_path_requires_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"PHOTO_ANALYZER_HF_VENDOR_ROOT": tmp}):
                with self.assertRaises(CaptioningError) as ctx:
                    resolve_local_vendor_model_path(MODEL_SPECS["balanced"])
                self.assertIn("vend_hf_models.py", str(ctx.exception))

    def test_local_vendor_model_path_ok_with_config_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "Salesforce_blip-image-captioning-large"
            sub.mkdir()
            (sub / "config.json").write_text('{"_test": true}', encoding="utf-8")
            with patch.dict(os.environ, {"PHOTO_ANALYZER_HF_VENDOR_ROOT": tmp}):
                path = resolve_local_vendor_model_path(MODEL_SPECS["balanced"])
                self.assertEqual(Path(path).resolve(), sub.resolve())

    def test_local_vendor_model_path_ok_for_git_large(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "Salesforce_blip2-opt-6.7b"
            sub.mkdir()
            (sub / "config.json").write_text('{"_test": true}', encoding="utf-8")
            with patch.dict(os.environ, {"PHOTO_ANALYZER_HF_VENDOR_ROOT": tmp}):
                path = resolve_local_vendor_model_path(MODEL_SPECS["git_large"])
                self.assertEqual(Path(path).resolve(), sub.resolve())

    def test_missing_file_raises_error(self) -> None:
        with self.assertRaises(AnalysisError):
            analyze_image("/tmp/does-not-exist-xyz.png")

    @patch("photo_analyzer.core.generate_caption", return_value="a warm portrait photo indoors")
    def test_analyze_image_returns_grouped_tags(self, _mock_caption: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (50, 40), (190, 120, 80)).save(path)
            result = analyze_image(str(path))

        self.assertEqual(result.image.orientation, "横图")
        self.assertEqual(result.caption, "a warm portrait photo indoors")
        self.assertIn("人像", result.tag_groups["subject_content"])
        self.assertIn("室内", result.tag_groups["scene_lighting"])
        self.assertIn("暖色调", result.tag_groups["style_impression"])
        self.assertLessEqual(len(result.tag_groups["subject_content"]), 2)
        self.assertLessEqual(len(result.tag_groups["scene_lighting"]), 2)
        self.assertEqual(result.metrics.temperature, "偏暖")
        self.assertIn("模型描述接近", result.summary)

    @patch("photo_analyzer.core.generate_caption", side_effect=RuntimeError("boom"))
    def test_analyze_image_falls_back_when_caption_fails(self, _mock_caption: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (40, 40), (20, 20, 25)).save(path)
            result = analyze_image(str(path))

        self.assertEqual(result.caption, "")
        self.assertTrue(
            bool(set(result.tag_groups["scene_lighting"]) & {"夜景", "低光"}),
        )
        self.assertTrue(result.errors)

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a close-up photo of flowers in a park at night with a cinematic mood",
    )
    def test_analyze_image_limits_to_two_tags_per_group(self, _mock_caption: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (120, 90), (180, 80, 100)).save(path)
            result = analyze_image(str(path))

        for group_name in TAG_GROUP_ORDER:
            self.assertLessEqual(len(result.tag_groups[group_name]), 2)
        self.assertIn("夜景", result.tag_groups["scene_lighting"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a black and white portrait of a runner in motion",
    )
    def test_analyze_image_detects_black_white_and_sports(self, _mock_caption: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (100, 140), (96, 96, 96)).save(path)
            result = analyze_image(str(path))

        self.assertIn("运动", result.tag_groups["subject_content"])
        self.assertIn("黑白", result.tag_groups["style_impression"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a man in sunglasses holding a camera",
    )
    def test_trigger_matching_avoids_substring_false_positive(self, _mock_caption: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (120, 160), (90, 90, 90)).save(path)
            result = analyze_image(str(path))

        self.assertIn("人像", result.tag_groups["subject_content"])
        self.assertNotIn("动物", result.tag_groups["subject_content"])

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a documentary portrait at a street stall",
    )
    def test_photo_model_uses_caption_mapping(self, _mock_caption: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (90, 140), (120, 120, 120)).save(path)
            result = analyze_image(str(path), model_key="photo")

        self.assertEqual(result.caption_model, "photo")
        self.assertEqual(result.caption, "a documentary portrait at a street stall")
        self.assertIn("人像", result.tag_groups["subject_content"])
        self.assertLessEqual(len(result.tag_groups["style_impression"]), 2)

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a dog running on a beach at sunset with dramatic clouds",
    )
    def test_git_large_model_uses_caption_mapping(self, _mock_caption: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (100, 80), (200, 160, 120)).save(path)
            result = analyze_image(str(path), model_key="git_large")

        self.assertEqual(result.caption_model, "git_large")
        self.assertEqual(result.caption_model_label, "BLIP-2 大")
        self.assertEqual(result.caption, "a dog running on a beach at sunset with dramatic clouds")
        self.assertTrue(
            bool(set(result.tag_groups["subject_content"]) & {"动物", "风光"}),
        )

    def test_missing_taxonomy_raises_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (40, 40), (50, 50, 50)).save(path)
            with patch("photo_analyzer.core.taxonomy_path", return_value=Path("/tmp/no-taxonomy.json")):
                with self.assertRaises(AnalysisError):
                    analyze_image(str(path))

    def test_disabled_taxonomy_tag_is_not_emitted(self) -> None:
        original = taxonomy_path().read_text(encoding="utf-8")
        payload = json.loads(original)
        for item in payload["tags"]:
            if item["label"] == "暖色调":
                item["enabled"] = False
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = Path(tmpdir) / "taxonomy.json"
            custom.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            with patch("photo_analyzer.core.taxonomy_path", return_value=custom):
                with patch("photo_analyzer.core.generate_caption", return_value="a warm portrait photo indoors"):
                    path = Path(tmpdir) / "x.png"
                    Image.new("RGB", (50, 40), (190, 120, 80)).save(path)
                    result = analyze_image(str(path))
        self.assertNotIn("暖色调", result.tags)

    # ------------------------------------------------------------------
    #  CLI / format / gallery tests
    # ------------------------------------------------------------------

    def test_format_result_shows_group_sections(self) -> None:
        load_taxonomy()
        result = AnalysisResult(
            image=ImageInfo(
                path="/tmp/x.png",
                format="PNG",
                width=100,
                height=200,
                orientation="竖图",
                aspect_ratio=0.5,
            ),
            metrics=ImageMetrics(
                brightness=22.1,
                contrast=12.4,
                saturation=45.3,
                temperature="偏暖",
                sharpness=8.2,
            ),
            caption="warm indoor portrait",
            caption_model="balanced",
            caption_model_label="平衡",
            model_initialization_seconds=0.0,
            analysis_duration_seconds=1.23,
            tag_groups={
                "subject_content": ["人像"],
                "scene_lighting": ["室内"],
                "composition_distance": ["近景"],
                "style_impression": ["暖色调"],
            },
            tags=["人像", "室内", "近景", "暖色调"],
            summary="测试摘要",
            analysis_version=ANALYSIS_VERSION,
            errors=[],
        )
        text = format_result(result)
        self.assertIn("题材 / 内容", text)
        self.assertIn("场景 / 光线", text)
        self.assertIn("色调倾向", text)
        self.assertIn("本地模型描述", text)
        self.assertNotIn("CLIP 标签", text)

    def test_gallery_item_shape(self) -> None:
        result = AnalysisResult(
            image=ImageInfo(
                path="/tmp/a.jpg",
                format="JPEG",
                width=10,
                height=10,
                orientation="方图",
                aspect_ratio=1.0,
            ),
            metrics=ImageMetrics(
                brightness=40.0,
                contrast=12.0,
                saturation=30.0,
                temperature="中性",
                sharpness=7.0,
            ),
            caption="a cup on a table",
            caption_model="fast",
            caption_model_label="快速",
            model_initialization_seconds=0.0,
            analysis_duration_seconds=0.84,
            tag_groups={
                "subject_content": ["人像"],
                "scene_lighting": ["室内"],
                "composition_distance": [],
                "style_impression": [],
            },
            tags=["人像", "室内"],
            summary="s",
            analysis_version=ANALYSIS_VERSION,
            errors=[],
        )
        item = build_gallery_item(result)
        self.assertEqual(item["caption"], "a cup on a table")
        self.assertIn("人像", item["tags"])
        self.assertIn("tag_groups", item)

    def test_desktop_app_helper_clamps_count_and_tags(self) -> None:
        result = AnalysisResult(
            image=ImageInfo(
                path="/tmp/a.jpg",
                format="JPEG",
                width=10,
                height=10,
                orientation="方图",
                aspect_ratio=1.0,
            ),
            metrics=ImageMetrics(
                brightness=40.0,
                contrast=12.0,
                saturation=30.0,
                temperature="中性",
                sharpness=7.0,
            ),
            caption="",
            caption_model="balanced",
            caption_model_label="平衡",
            model_initialization_seconds=0.0,
            analysis_duration_seconds=0.12,
            tag_groups={group: [] for group in TAG_GROUP_ORDER},
            tags=[],
            summary="s",
            analysis_version=ANALYSIS_VERSION,
            errors=[],
        )
        self.assertEqual(build_card_tags(result), ["无描述标签"])
        self.assertEqual(clamp_sample_count("999"), MAX_SAMPLE_COUNT)
        self.assertEqual(clamp_sample_count("0"), 1)
        self.assertEqual(clamp_sample_count("abc"), 100)

    def test_cli_outputs_grouped_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.png"
            Image.new("RGB", (64, 64), (200, 180, 160)).save(path)
            env = os.environ.copy()
            env.update(TEST_ENV)
            completed = subprocess.run(
                [sys.executable, "-m", "photo_analyzer", "analyze", str(path)],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=env,
            )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("总体判断：", completed.stdout)
        self.assertIn("题材 / 内容", completed.stdout)
        self.assertIn("场景 / 光线", completed.stdout)
        self.assertIn("色调倾向", completed.stdout)
        self.assertIn("分析信息", completed.stdout)
        self.assertNotIn("横幅感", completed.stdout)
        self.assertNotIn("CLIP", completed.stdout)

    def test_cli_analyze_accepts_git_large_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (48, 48), (90, 90, 90)).save(path)
            env = os.environ.copy()
            env.update(TEST_ENV)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "photo_analyzer",
                    "analyze",
                    str(path),
                    "--model",
                    "git_large",
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=env,
            )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("BLIP-2 大", completed.stdout)
        self.assertIn("git_large", completed.stdout)

    def test_cli_version_flag(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "photo_analyzer", "--version"],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("1.2.1", completed.stdout)

    def test_cli_accepts_directory_for_batch_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            Image.new("RGB", (60, 60), (220, 180, 120)).save(folder / "a.png")
            Image.new("RGB", (60, 60), (35, 35, 60)).save(folder / "b.jpg")
            (folder / "notes.txt").write_text("ignore", encoding="utf-8")
            env = os.environ.copy()
            env.update(TEST_ENV)

            completed = subprocess.run(
                [sys.executable, "-m", "photo_analyzer", "analyze", str(folder)],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=env,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("=== a.png ===", completed.stdout)
        self.assertIn("=== b.jpg ===", completed.stdout)
        self.assertEqual(completed.stdout.count("总体判断："), 2)

    def test_sample_gallery_generates_html_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "images"
            output = Path(tmpdir) / "export"
            folder.mkdir()
            Image.new("RGB", (60, 60), (220, 180, 120)).save(folder / "a.png")
            Image.new("RGB", (60, 60), (35, 35, 60)).save(folder / "b.jpg")
            env = os.environ.copy()
            env.update(TEST_ENV)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "photo_analyzer",
                    "sample-gallery",
                    str(folder),
                    "--count",
                    "2",
                    "--seed",
                    "123",
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=env,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            html_path = output / "index.html"
            json_path = output / "results.json"
            self.assertTrue(html_path.exists())
            self.assertTrue(json_path.exists())

            json_text = json_path.read_text(encoding="utf-8")
            html_text = html_path.read_text(encoding="utf-8")
            payload = json.loads(json_text)
            self.assertEqual(payload["sample_count"], 2)
            self.assertIn('"tag_groups"', json_text)
            self.assertIn('"caption": "a warm portrait photo indoors"', json_text)
            self.assertIn('"caption_model": "balanced"', json_text)
            self.assertIn('"model_initialization_seconds"', json_text)
            self.assertIn('"analysis_duration_seconds"', json_text)
            self.assertIn("测试照片数（最大 100）", html_text)
            self.assertNotIn("--top-k", html_text)
            self.assertIn("a.png", html_text)

    def test_sample_gallery_rejects_count_over_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "images"
            folder.mkdir()
            Image.new("RGB", (40, 40), (200, 200, 200)).save(folder / "a.png")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "photo_analyzer",
                    "sample-gallery",
                    str(folder),
                    "--count",
                    "101",
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path(__file__).resolve().parents[1],
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("抽样数量不能超过 100", completed.stderr)

    def test_local_html_tool_exists_with_required_controls(self) -> None:
        html_path = Path(__file__).resolve().parents[1] / "local_gallery.html"
        html_text = html_path.read_text(encoding="utf-8")

        self.assertTrue(html_path.exists())
        self.assertIn('id="results-button"', html_text)
        self.assertIn("showDirectoryPicker", html_text)
        self.assertIn('id="count-input"', html_text)
        self.assertIn('max="100"', html_text)
        self.assertIn("开始展示结果", html_text)
        self.assertIn("results.json", html_text)
        self.assertIn("选择结果目录", html_text)
        self.assertIn("toImageSrc", html_text)
        self.assertIn("renderGallery", html_text)
        self.assertNotIn("extractFeatures", html_text)
        self.assertNotIn("buildTags", html_text)

    def test_desktop_app_entrypoints_exist(self) -> None:
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        pyproject_text = pyproject_path.read_text(encoding="utf-8")

        self.assertIn('photo-analyzer-app = "photo_analyzer.desktop_app:main"', pyproject_text)
        self.assertIn('"app", help="启动本地桌面标签画廊，无需 web service"', Path(
            __file__).resolve().parents[1].joinpath("photo_analyzer", "cli.py").read_text(encoding="utf-8"))
        self.assertIn("taxonomy.json", pyproject_text)
        content_view_text = Path(__file__).resolve().parents[1].joinpath(
            "PhotoAnalyzerApp", "Sources", "ContentView.swift"
        ).read_text(encoding="utf-8")
        self.assertIn('VersionPill(title: "UI"', content_view_text)
        self.assertIn('VersionPill(title: "CLI"', content_view_text)
        self.assertIn('GroupedTagSection(title: "题材 / 内容"', content_view_text)
        self.assertIn('GroupedTagSection(title: "色调倾向"', content_view_text)
        self.assertIn('Picker("模型"', content_view_text)
        self.assertIn("本次分析", content_view_text)
        self.assertIn("model_download_progress", Path(
            __file__).resolve().parents[1].joinpath("PhotoAnalyzerApp", "Sources", "AnalyzerService.swift"
        ).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
