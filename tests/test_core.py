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
    analyze_image,
    load_taxonomy,
    taxonomy_path,
)
from photo_analyzer.desktop_app import MAX_SAMPLE_COUNT, build_card_tags, clamp_sample_count


TEST_ENV = {"PHOTO_ANALYZER_CAPTION_OVERRIDE": "a warm portrait photo indoors"}


class PhotoAnalyzerTests(unittest.TestCase):
    def test_taxonomy_loads_four_groups(self) -> None:
        definitions = load_taxonomy()
        self.assertTrue(definitions)
        self.assertEqual({item.group for item in definitions}, set(TAG_GROUP_ORDER))
        self.assertTrue(any(item.label == "人像" for item in definitions))
        self.assertTrue(any(item.label == "单人肖像" for item in definitions))
        self.assertTrue(any(item.label == "蓝调时刻" for item in definitions))
        self.assertTrue(any(item.label == "黑白倾向" for item in definitions))

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
        self.assertIn("暖调风格", result.tag_groups["style_impression"])
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
        self.assertTrue(result.tag_groups["scene_lighting"])
        self.assertIn("低光环境", result.tag_groups["scene_lighting"])
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
        self.assertIn("夜间场景", result.tag_groups["scene_lighting"])
        self.assertIn("特写", result.tag_groups["composition_distance"])

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
        self.assertIn("动态构图", result.tag_groups["composition_distance"])
        self.assertIn("黑白倾向", result.tag_groups["style_impression"])

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
        self.assertNotIn("饮品", result.tag_groups["subject_content"])

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
        self.assertTrue(
            "街拍人物" in result.tag_groups["subject_content"] or "街拍" in result.tag_groups["subject_content"]
        )

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
        self.assertIn("宠物", result.tag_groups["subject_content"])
        self.assertIn("海边", result.tag_groups["scene_lighting"])

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
        for item in payload["categories"]["style_impression"]:
            if item["label"] == "暖调风格":
                item["enabled"] = False
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = Path(tmpdir) / "taxonomy.json"
            custom.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            with patch("photo_analyzer.core.taxonomy_path", return_value=custom):
                with patch("photo_analyzer.core.generate_caption", return_value="a warm portrait photo indoors"):
                    path = Path(tmpdir) / "x.png"
                    Image.new("RGB", (50, 40), (190, 120, 80)).save(path)
                    result = analyze_image(str(path))
        self.assertNotIn("暖调风格", result.tags)

    def test_custom_taxonomy_tag_can_be_added(self) -> None:
        original = taxonomy_path().read_text(encoding="utf-8")
        payload = json.loads(original)
        payload["categories"]["subject_content"].append(
            {
                "id": "flowers",
                "label": "花卉",
                "group": "subject_content",
                "enabled": True,
                "trigger_terms": ["flower", "flowers", "tulip"],
                "metric_rules": {},
                "summary_priority": 9,
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = Path(tmpdir) / "taxonomy.json"
            custom.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            with patch("photo_analyzer.core.taxonomy_path", return_value=custom):
                with patch("photo_analyzer.core.generate_caption", return_value="a close-up of yellow tulip flowers"):
                    path = Path(tmpdir) / "x.png"
                    Image.new("RGB", (60, 60), (180, 180, 60)).save(path)
                    result = analyze_image(str(path))
        self.assertIn("花卉", result.tags)

    def test_format_result_shows_group_sections(self) -> None:
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
                "subject_content": ["静物"],
                "scene_lighting": ["室内"],
                "composition_distance": [],
                "style_impression": [],
            },
            tags=["静物", "室内"],
            summary="s",
            analysis_version=ANALYSIS_VERSION,
            errors=[],
        )
        item = build_gallery_item(result)
        self.assertEqual(item["caption"], "a cup on a table")
        self.assertIn("静物", item["tags"])
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
        self.assertIn('Picker("模型"', content_view_text)
        self.assertIn("本次分析", content_view_text)
        self.assertIn("model_download_progress", Path(
            __file__).resolve().parents[1].joinpath("PhotoAnalyzerApp", "Sources", "AnalyzerService.swift"
        ).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
