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

TEST_ENV = {"PHOTO_ANALYZER_CAPTION_OVERRIDE": "a warm portrait photo indoors"}


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _make_image(tmpdir: str, size: tuple = (100, 100), color: tuple = (128, 128, 128),
                name: str = "x.png") -> str:
    path = Path(tmpdir) / name
    Image.new("RGB", size, color).save(path)
    return str(path)


def _analyze_caption(caption: str, size: tuple = (100, 100),
                     color: tuple = (128, 128, 128), **kwargs) -> AnalysisResult:
    with patch("photo_analyzer.core.generate_caption", return_value=caption):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_image(tmpdir, size, color)
            return analyze_image(path, **kwargs)


def _quick_signals(caption: str, **metric_overrides) -> Signals:
    defaults = dict(brightness=50.0, contrast=12.0, saturation=30.0,
                    temperature="中性", sharpness=10.0)
    defaults.update(metric_overrides)
    return extract_signals(caption, ImageMetrics(**defaults), aspect_ratio=1.0)


# ===================================================================
#  Layer 2/3: Scoring + Selection
# ===================================================================

class TestScoringAndSelection(unittest.TestCase):

    def test_portrait_token_scores(self) -> None:
        taxonomy = load_taxonomy()
        scores = score_all_tags(taxonomy, _quick_signals("a woman standing in a garden"))
        self.assertGreater(scores.get("人像", 0), 0)

    def test_animal_dog_token_scores(self) -> None:
        taxonomy = load_taxonomy()
        scores = score_all_tags(taxonomy, _quick_signals("a dog laying on the grass"))
        self.assertGreater(scores.get("动物", 0), 0)

    def test_women_plural_triggers_portrait(self) -> None:
        taxonomy = load_taxonomy()
        scores = score_all_tags(taxonomy, _quick_signals("two women holding up a lighted object"))
        self.assertGreater(scores.get("人像", 0), 0)

    def test_conflict_indoor_outdoor(self) -> None:
        taxonomy = load_taxonomy()
        tag_groups = select_tags({"室内": 1.0, "室外": 0.8}, taxonomy)
        self.assertIn("室内", tag_groups["scene_lighting"])
        self.assertNotIn("室外", tag_groups["scene_lighting"])

    def test_conflict_close_up_vs_medium(self) -> None:
        taxonomy = load_taxonomy()
        tag_groups = select_tags({"特写": 1.0, "近景": 0.9, "对称": 0.5}, taxonomy)
        comp = tag_groups["composition_distance"]
        self.assertIn("特写", comp)
        self.assertNotIn("近景", comp)
        self.assertIn("对称", comp)

    def test_conflict_warm_cool(self) -> None:
        taxonomy = load_taxonomy()
        tag_groups = select_tags({"暖色调": 1.0, "冷色调": 0.8, "明亮": 0.5}, taxonomy)
        style = tag_groups["style_impression"]
        self.assertIn("暖色调", style)
        self.assertNotIn("冷色调", style)

    def test_conflict_bw_excludes_saturation(self) -> None:
        taxonomy = load_taxonomy()
        tag_groups = select_tags({"黑白": 1.5, "高饱和": 0.5}, taxonomy)
        style = tag_groups["style_impression"]
        self.assertIn("黑白", style)
        self.assertNotIn("高饱和", style)

    def test_max_tags_per_group(self) -> None:
        taxonomy = load_taxonomy()
        tag_groups = select_tags(
            {"人像": 1.0, "建筑": 0.9, "风光": 0.8, "食物": 0.7}, taxonomy,
        )
        self.assertLessEqual(len(tag_groups["subject_content"]), 2)


# ===================================================================
#  Refinements
# ===================================================================

class TestRefinements(unittest.TestCase):

    def test_drops_portrait_for_weak_person_plus_food(self) -> None:
        taxonomy = load_taxonomy()
        signals = _quick_signals("a person is cutting a fruit tart with a knife")
        tag_groups = select_tags(score_all_tags(taxonomy, signals), taxonomy)
        refined = _refine_subject_food_vs_portrait(signals, tag_groups)
        self.assertNotIn("人像", refined["subject_content"])
        self.assertIn("食物", refined["subject_content"])

    def test_keeps_portrait_when_woman_and_food(self) -> None:
        taxonomy = load_taxonomy()
        signals = _quick_signals("a woman decorating a fruit tart in a kitchen")
        tag_groups = select_tags(score_all_tags(taxonomy, signals), taxonomy)
        refined = _refine_subject_food_vs_portrait(signals, tag_groups)
        self.assertIn("人像", refined["subject_content"])


# ===================================================================
#  Integration: full pipeline via analyze_image
# ===================================================================

class TestAnalyzeImagePipeline(unittest.TestCase):

    def test_bird_maps_to_animal(self) -> None:
        r = _analyze_caption("a colorful bird perched on a branch in the forest",
                             color=(40, 80, 40))
        self.assertIn("动物", r.tag_groups["subject_content"])

    def test_macro_butterfly_emits_animal_and_macro(self) -> None:
        r = _analyze_caption("a macro close up of a butterfly resting on a leaf",
                             color=(50, 70, 40))
        self.assertIn("动物", r.tag_groups["subject_content"])
        self.assertIn("微距", r.tag_groups["composition_distance"])

    def test_dog_maps_to_animal(self) -> None:
        r = _analyze_caption("a dog laying on the grass", color=(90, 90, 90))
        self.assertIn("动物", r.tag_groups["subject_content"])

    def test_two_people_maps_to_portrait(self) -> None:
        r = _analyze_caption(
            "there are two people standing in front of a building with columns",
            size=(90, 140), color=(110, 105, 95),
        )
        self.assertIn("人像", r.tag_groups["subject_content"])

    def test_roses_map_to_landscape_no_conflicting_close(self) -> None:
        r = _analyze_caption("a close up of two red roses on a stem",
                             color=(90, 40, 50))
        self.assertIn("风光", r.tag_groups["subject_content"])
        comp = set(r.tag_groups["composition_distance"])
        self.assertFalse(comp >= {"特写", "近景"})

    def test_man_with_cart_maps_to_portrait(self) -> None:
        r = _analyze_caption("a man pushing a cart with a bunch of stuff on it",
                             size=(90, 140), color=(110, 105, 95))
        self.assertIn("人像", r.tag_groups["subject_content"])

    def test_woman_with_baby_maps_to_portrait(self) -> None:
        r = _analyze_caption("a woman holding a baby in a stroller",
                             size=(90, 140), color=(110, 105, 95))
        self.assertIn("人像", r.tag_groups["subject_content"])

    def test_city_skyline_maps_to_architecture(self) -> None:
        r = _analyze_caption("a city skyline with a bridge",
                             size=(200, 120), color=(80, 90, 110))
        self.assertIn("建筑", r.tag_groups["subject_content"])

    def test_bridge_over_water_maps_to_architecture(self) -> None:
        r = _analyze_caption("a bridge over a body of water",
                             size=(200, 120), color=(80, 90, 110))
        self.assertIn("建筑", r.tag_groups["subject_content"])

    def test_go_kart_maps_to_sports(self) -> None:
        r = _analyze_caption("two people in go kart racing gear on a track",
                             size=(200, 120), color=(80, 90, 70))
        self.assertIn("运动", r.tag_groups["subject_content"])

    def test_bw_portrait_gets_bw_style(self) -> None:
        r = _analyze_caption("a black and white portrait of a woman",
                             size=(200, 120), color=(90, 90, 90))
        self.assertIn("黑白", r.tag_groups["style_impression"])

    def test_glass_sculpture_empty_subject(self) -> None:
        r = _analyze_caption("a tall glass sculpture with a lot of lights",
                             size=(90, 140), color=(40, 40, 60))
        self.assertEqual(r.tag_groups["subject_content"], [])

    def test_chinese_new_year_tags_in_allowed_vocabulary(self) -> None:
        r = _analyze_caption("a red and gold chinese new year decoration",
                             size=(80, 80), color=(180, 40, 40))
        self.assertTrue(set(r.tags) <= ALLOWED_TAXONOMY_LABELS)

    def test_walkway_to_field_maps_to_landscape(self) -> None:
        r = _analyze_caption("a wooden walkway leads to a grassy field",
                             size=(200, 100), color=(60, 90, 50))
        self.assertIn("风光", r.tag_groups["subject_content"])

    def test_figurine_does_not_emit_animal(self) -> None:
        r = _analyze_caption("there are many cow figurines on display in a glass case",
                             size=(80, 80), color=(60, 55, 50))
        self.assertNotIn("动物", r.tag_groups["subject_content"])

    def test_food_plate_maps_to_food(self) -> None:
        r = _analyze_caption("there is a plate of food with meat and vegetables on it",
                             size=(200, 120), color=(140, 100, 80))
        self.assertIn("食物", r.tag_groups["subject_content"])

    def test_sunglasses_avoids_animal_false_positive(self) -> None:
        r = _analyze_caption("a man in sunglasses holding a camera",
                             size=(120, 160), color=(90, 90, 90))
        self.assertIn("人像", r.tag_groups["subject_content"])
        self.assertNotIn("动物", r.tag_groups["subject_content"])

    def test_warm_portrait_indoors_full_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_image(tmpdir, (50, 40), (190, 120, 80))
            with patch("photo_analyzer.core.generate_caption",
                       return_value="a warm portrait photo indoors"):
                result = analyze_image(path)

        self.assertEqual(result.image.orientation, "横图")
        self.assertEqual(result.caption, "a warm portrait photo indoors")
        self.assertIn("人像", result.tag_groups["subject_content"])
        self.assertIn("室内", result.tag_groups["scene_lighting"])
        self.assertIn("暖色调", result.tag_groups["style_impression"])
        self.assertLessEqual(len(result.tag_groups["subject_content"]), 2)
        self.assertLessEqual(len(result.tag_groups["scene_lighting"]), 2)
        self.assertEqual(result.metrics.temperature, "偏暖")
        self.assertIn("模型描述接近", result.summary)

    def test_caption_failure_falls_back_to_metrics(self) -> None:
        with patch("photo_analyzer.core.generate_caption", side_effect=RuntimeError("boom")):
            with tempfile.TemporaryDirectory() as tmpdir:
                path = _make_image(tmpdir, (40, 40), (20, 20, 25))
                result = analyze_image(path)

        self.assertEqual(result.caption, "")
        self.assertTrue(
            bool(set(result.tag_groups["scene_lighting"]) & {"夜景", "低光"}),
        )
        self.assertTrue(result.errors)

    def test_limits_two_tags_per_group(self) -> None:
        r = _analyze_caption(
            "a close-up photo of flowers in a park at night with a cinematic mood",
            size=(120, 90), color=(180, 80, 100),
        )
        for group_name in TAG_GROUP_ORDER:
            self.assertLessEqual(len(r.tag_groups[group_name]), 2)
        self.assertIn("夜景", r.tag_groups["scene_lighting"])

    def test_bw_runner_detects_sports_and_bw(self) -> None:
        r = _analyze_caption("a black and white portrait of a runner in motion",
                             size=(100, 140), color=(96, 96, 96))
        self.assertIn("运动", r.tag_groups["subject_content"])
        self.assertIn("黑白", r.tag_groups["style_impression"])

    def test_photo_model_key_uses_caption_mapping(self) -> None:
        r = _analyze_caption("a documentary portrait at a street stall",
                             size=(90, 140), color=(120, 120, 120),
                             model_key="photo")
        self.assertEqual(r.caption_model, "photo")
        self.assertIn("人像", r.tag_groups["subject_content"])
        self.assertLessEqual(len(r.tag_groups["style_impression"]), 2)

    def test_git_large_model_key_uses_caption_mapping(self) -> None:
        r = _analyze_caption(
            "a dog running on a beach at sunset with dramatic clouds",
            size=(100, 80), color=(200, 160, 120),
            model_key="git_large",
        )
        self.assertEqual(r.caption_model, "git_large")
        self.assertEqual(r.caption_model_label, "BLIP-2 大")
        self.assertTrue(
            bool(set(r.tag_groups["subject_content"]) & {"动物", "风光"}),
        )


# ===================================================================
#  Taxonomy structure
# ===================================================================

class TestTaxonomy(unittest.TestCase):

    def test_loads_four_groups_and_26_tags(self) -> None:
        taxonomy = load_taxonomy()
        self.assertEqual(taxonomy.version, 2)
        self.assertEqual(len(taxonomy.groups), 4)
        self.assertEqual({g.name for g in taxonomy.groups}, set(TAG_GROUP_ORDER))
        self.assertEqual(len(taxonomy.tags), 26)
        labels = {t.label for t in taxonomy.tags}
        self.assertTrue(labels <= ALLOWED_TAXONOMY_LABELS)

    def test_all_tags_belong_to_valid_groups(self) -> None:
        taxonomy = load_taxonomy()
        valid_groups = {g.name for g in taxonomy.groups}
        for tag in taxonomy.tags:
            self.assertIn(tag.group, valid_groups,
                          f"Tag {tag.label} has invalid group {tag.group}")

    def test_conflicts_reference_existing_labels(self) -> None:
        taxonomy = load_taxonomy()
        all_labels = {t.label for t in taxonomy.tags}
        for tag in taxonomy.tags:
            for conflict_label in tag.conflicts:
                self.assertIn(conflict_label, all_labels,
                              f"{tag.label} declares conflict with unknown label {conflict_label}")

    def test_missing_taxonomy_raises_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_image(tmpdir)
            with patch("photo_analyzer.core.taxonomy_path",
                       return_value=Path("/tmp/no-taxonomy.json")):
                with self.assertRaises(AnalysisError):
                    analyze_image(path)

    def test_disabled_tag_not_emitted(self) -> None:
        original = taxonomy_path().read_text(encoding="utf-8")
        payload = json.loads(original)
        for item in payload["tags"]:
            if item["label"] == "暖色调":
                item["enabled"] = False
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = Path(tmpdir) / "taxonomy.json"
            custom.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                              encoding="utf-8")
            with patch("photo_analyzer.core.taxonomy_path", return_value=custom):
                with patch("photo_analyzer.core.generate_caption",
                           return_value="a warm portrait photo indoors"):
                    path = _make_image(tmpdir, (50, 40), (190, 120, 80))
                    result = analyze_image(path)
        self.assertNotIn("暖色调", result.tags)


# ===================================================================
#  Captioning / model resolution
# ===================================================================

class TestCaptioning(unittest.TestCase):

    def test_photo_and_git_large_presets_exist(self) -> None:
        keys = [item.key for item in available_caption_models()]
        self.assertIn("photo", keys)
        self.assertIn("git_large", keys)

    def test_vendor_path_requires_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"PHOTO_ANALYZER_HF_VENDOR_ROOT": tmp}):
                with self.assertRaises(CaptioningError) as ctx:
                    resolve_local_vendor_model_path(MODEL_SPECS["balanced"])
                self.assertIn("vend_hf_models.py", str(ctx.exception))

    def test_vendor_path_ok_with_config_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "Salesforce_blip-image-captioning-large"
            sub.mkdir()
            (sub / "config.json").write_text('{"_test": true}', encoding="utf-8")
            with patch.dict(os.environ, {"PHOTO_ANALYZER_HF_VENDOR_ROOT": tmp}):
                path = resolve_local_vendor_model_path(MODEL_SPECS["balanced"])
                self.assertEqual(Path(path).resolve(), sub.resolve())

    def test_vendor_path_ok_for_git_large(self) -> None:
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


# ===================================================================
#  CLI / format / gallery
# ===================================================================

class TestCLI(unittest.TestCase):

    def test_format_result_shows_group_sections(self) -> None:
        load_taxonomy()
        result = AnalysisResult(
            image=ImageInfo(
                path="/tmp/x.png", format="PNG",
                width=100, height=200, orientation="竖图", aspect_ratio=0.5,
            ),
            metrics=ImageMetrics(
                brightness=22.1, contrast=12.4, saturation=45.3,
                temperature="偏暖", sharpness=8.2,
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
                path="/tmp/a.jpg", format="JPEG",
                width=10, height=10, orientation="方图", aspect_ratio=1.0,
            ),
            metrics=ImageMetrics(
                brightness=40.0, contrast=12.0, saturation=30.0,
                temperature="中性", sharpness=7.0,
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

    def test_desktop_app_clamps_count_and_tags(self) -> None:
        result = AnalysisResult(
            image=ImageInfo(
                path="/tmp/a.jpg", format="JPEG",
                width=10, height=10, orientation="方图", aspect_ratio=1.0,
            ),
            metrics=ImageMetrics(
                brightness=40.0, contrast=12.0, saturation=30.0,
                temperature="中性", sharpness=7.0,
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
            path = _make_image(tmpdir, (64, 64), (200, 180, 160))
            env = {**os.environ, **TEST_ENV}
            completed = subprocess.run(
                [sys.executable, "-m", "photo_analyzer", "analyze", path],
                capture_output=True, text=True, check=False,
                cwd=Path(__file__).resolve().parents[1], env=env,
            )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("总体判断：", completed.stdout)
        self.assertIn("题材 / 内容", completed.stdout)

    def test_cli_analyze_accepts_git_large_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _make_image(tmpdir, (48, 48), (90, 90, 90))
            env = {**os.environ, **TEST_ENV}
            completed = subprocess.run(
                [sys.executable, "-m", "photo_analyzer", "analyze", path,
                 "--model", "git_large"],
                capture_output=True, text=True, check=False,
                cwd=Path(__file__).resolve().parents[1], env=env,
            )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("BLIP-2 大", completed.stdout)

    def test_cli_version_flag(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "photo_analyzer", "--version"],
            capture_output=True, text=True, check=False,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("1.2.1", completed.stdout)

    def test_cli_accepts_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            Image.new("RGB", (60, 60), (220, 180, 120)).save(folder / "a.png")
            Image.new("RGB", (60, 60), (35, 35, 60)).save(folder / "b.jpg")
            (folder / "notes.txt").write_text("ignore", encoding="utf-8")
            env = {**os.environ, **TEST_ENV}
            completed = subprocess.run(
                [sys.executable, "-m", "photo_analyzer", "analyze", str(folder)],
                capture_output=True, text=True, check=False,
                cwd=Path(__file__).resolve().parents[1], env=env,
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
            env = {**os.environ, **TEST_ENV}
            completed = subprocess.run(
                [sys.executable, "-m", "photo_analyzer", "sample-gallery",
                 str(folder), "--count", "2", "--seed", "123",
                 "--output-dir", str(output)],
                capture_output=True, text=True, check=False,
                cwd=Path(__file__).resolve().parents[1], env=env,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)

            json_path = output / "results.json"
            self.assertTrue(json_path.exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["sample_count"], 2)
            self.assertIn("tag_groups", payload["items"][0])

    def test_sample_gallery_rejects_count_over_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "images"
            folder.mkdir()
            Image.new("RGB", (40, 40), (200, 200, 200)).save(folder / "a.png")
            completed = subprocess.run(
                [sys.executable, "-m", "photo_analyzer", "sample-gallery",
                 str(folder), "--count", "101"],
                capture_output=True, text=True, check=False,
                cwd=Path(__file__).resolve().parents[1],
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("抽样数量不能超过 100", completed.stderr)

    def test_desktop_app_entrypoint_in_pyproject(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        self.assertIn("photo-analyzer-app", text)
        self.assertIn("taxonomy.json", text)


if __name__ == "__main__":
    unittest.main()
