import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from photo_analyzer.cli import build_gallery_item, format_result
from photo_analyzer.core import (
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
    def test_taxonomy_loads(self) -> None:
        definitions = load_taxonomy()
        self.assertTrue(definitions)
        self.assertTrue(any(item.label == "人像" for item in definitions))

    def test_missing_file_raises_error(self) -> None:
        with self.assertRaises(AnalysisError):
            analyze_image("/tmp/does-not-exist-xyz.png")

    @patch("photo_analyzer.core.generate_caption", return_value="a warm portrait photo indoors")
    def test_analyze_image_returns_caption_metrics_and_tags(self, _mock_caption: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (50, 40), (190, 120, 80)).save(path)
            result = analyze_image(str(path))

        self.assertEqual(result.image.orientation, "横图")
        self.assertEqual(result.caption, "a warm portrait photo indoors")
        self.assertTrue(result.tags)
        self.assertIn("人像", result.tags)
        self.assertEqual(result.metrics.temperature, "偏暖")
        self.assertIn("模型描述接近", result.summary)
        self.assertIn("室内场景", result.tags)

    @patch("photo_analyzer.core.generate_caption", side_effect=RuntimeError("boom"))
    def test_analyze_image_falls_back_when_caption_fails(self, _mock_caption: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (40, 40), (20, 20, 25)).save(path)
            result = analyze_image(str(path))

        self.assertEqual(result.caption, "")
        self.assertTrue(result.tags)
        self.assertIn("低光", result.tags)
        self.assertTrue(result.errors)

    @patch(
        "photo_analyzer.core.generate_caption",
        return_value="a close-up photo of flowers in a park at night",
    )
    def test_analyze_image_expands_subject_scene_and_mood_tags(self, _mock_caption: object) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.png"
            Image.new("RGB", (120, 90), (180, 80, 100)).save(path)
            result = analyze_image(str(path))

        self.assertIn("花卉植物", result.tags)
        self.assertIn("室外场景", result.tags)
        self.assertIn("夜景", result.tags)
        self.assertIn("近景特写", result.tags)

    def test_missing_taxonomy_raises_error(self) -> None:
        with patch("photo_analyzer.core.taxonomy_path", return_value=Path("/tmp/no-taxonomy.json")):
            with self.assertRaises(AnalysisError):
                analyze_image("/tmp/does-not-exist-xyz.png")

    def test_disabled_taxonomy_tag_is_not_emitted(self) -> None:
        original = taxonomy_path().read_text(encoding="utf-8")
        payload = json.loads(original)
        for item in payload["categories"]["style"]:
            if item["label"] == "偏暖":
                item["enabled"] = False
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = Path(tmpdir) / "taxonomy.json"
            custom.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            with patch("photo_analyzer.core.taxonomy_path", return_value=custom):
                with patch("photo_analyzer.core.generate_caption", return_value="a warm portrait photo indoors"):
                    path = Path(tmpdir) / "x.png"
                    Image.new("RGB", (50, 40), (190, 120, 80)).save(path)
                    result = analyze_image(str(path))
        self.assertNotIn("偏暖", result.tags)

    def test_custom_taxonomy_tag_can_be_added(self) -> None:
        original = taxonomy_path().read_text(encoding="utf-8")
        payload = json.loads(original)
        payload["categories"]["subject"].append(
            {
                "id": "craft_tools",
                "label": "手作工具",
                "group": "subject",
                "enabled": True,
                "trigger_terms": ["scissors", "tool", "craft"],
                "metric_rules": {},
                "summary_priority": 24,
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = Path(tmpdir) / "taxonomy.json"
            custom.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            with patch("photo_analyzer.core.taxonomy_path", return_value=custom):
                with patch("photo_analyzer.core.generate_caption", return_value="a bunch of scissors on a table"):
                    path = Path(tmpdir) / "x.png"
                    Image.new("RGB", (60, 60), (110, 110, 110)).save(path)
                    result = analyze_image(str(path))
        self.assertIn("手作工具", result.tags)

    def test_format_result_shows_metrics_and_caption(self) -> None:
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
            caption="a warm portrait photo indoors",
            tags=["人像", "偏暖"],
            summary="测试摘要",
            analysis_version="1.0.0",
            errors=[],
        )
        text = format_result(result)
        self.assertIn("描述标签", text)
        self.assertIn("本地模型描述", text)
        self.assertIn("亮度：22.1", text)
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
            tags=["静物物件"],
            summary="s",
            analysis_version="1.0.0",
            errors=[],
        )
        item = build_gallery_item(result)
        self.assertEqual(item["caption"], "a cup on a table")
        self.assertIn("静物物件", item["tags"])
        self.assertNotIn("semantic_tags", item)

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
            tags=[],
            summary="s",
            analysis_version="1.0.0",
            errors=[],
        )
        self.assertEqual(build_card_tags(result), ["无描述标签"])
        self.assertEqual(clamp_sample_count("999"), MAX_SAMPLE_COUNT)
        self.assertEqual(clamp_sample_count("0"), 1)
        self.assertEqual(clamp_sample_count("abc"), 100)

    def test_cli_outputs_new_sections(self) -> None:
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
        self.assertIn("描述标签", completed.stdout)
        self.assertIn("本地模型描述", completed.stdout)
        self.assertNotIn("CLIP", completed.stdout)

    def test_cli_version_flag(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "photo_analyzer", "--version"],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("1.0.0", completed.stdout)

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
            self.assertIn('"file_name": "a.png"', json_text)
            self.assertIn('"caption": "a warm portrait photo indoors"', json_text)
            self.assertNotIn('"top_k"', json_text)
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


if __name__ == "__main__":
    unittest.main()
