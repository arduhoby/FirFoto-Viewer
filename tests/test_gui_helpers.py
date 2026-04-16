from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from firfoto.cli import build_parser
from firfoto.core.models import AnalysisMetrics, AnalysisReason, AnalysisResult, Decision, FileIdentity, PhotoCategory, SubjectHints
from firfoto.gui.formatters import format_af_lines, format_capture_lines, format_identity_lines, format_metric_lines, format_quality, format_reason_lines
from firfoto.gui.image_loader import focus_point_from_nikon_label, focus_rects_from_nikon_label, load_preview_frame


class GuiHelperTests(unittest.TestCase):
    def test_parser_includes_gui_command(self) -> None:
        parser = build_parser()
        namespace = parser.parse_args(["gui"])
        self.assertEqual(namespace.command, "gui")

    def test_format_quality(self) -> None:
        self.assertEqual(format_quality(None), "n/a")
        self.assertEqual(format_quality(0.12345), "0.123")

    def test_formatters_render_result(self) -> None:
        result = AnalysisResult(
            identity=FileIdentity(path=Path("/tmp/test.jpg"), size_bytes=1234, sha256="abc"),
            decision=Decision.SELECTED,
            hints=SubjectHints(category=PhotoCategory.BIRD, subject_label="bird"),
        )
        result.camera.maker = "Nikon"
        result.camera.model = "D5"
        result.lens.model = "500mm"
        result.metrics = AnalysisMetrics(
            sharpness=0.5,
            exposure=0.6,
            contrast=0.7,
            noise=0.2,
            motion_blur_probability=0.1,
            overall_quality=0.8,
        )
        result.reasons = [AnalysisReason(code="ok", message="Looks fine")]

        self.assertIn("Kategori: bird", format_identity_lines(result))
        self.assertIn("Genel kalite: 0.800", format_metric_lines(result))
        self.assertIn("INFO: Looks fine", format_reason_lines(result))

    def test_format_capture_lines(self) -> None:
        result = AnalysisResult(
            identity=FileIdentity(path=Path("/tmp/test.jpg"), size_bytes=1234, sha256="abc"),
            decision=Decision.SELECTED,
            hints=SubjectHints(category=PhotoCategory.BIRD, subject_label="bird"),
        )
        result.camera.maker = "Nikon"
        result.camera.model = "D5"
        result.lens.maker = "Nikon"
        result.lens.model = "AF-S 500mm"
        result.lens.focal_length_mm = 500
        result.lens.aperture_f = 4.0
        result.extras["image_width"] = 4000
        result.extras["image_height"] = 3000
        result.extras["exposure_time_s"] = 0.002
        result.extras["iso"] = 800

        lines = format_capture_lines(result)
        self.assertIn("Çözünürlük: 4000 x 3000", lines)
        self.assertIn("Odak uzaklığı: 500 mm", lines)
        self.assertIn("Açıklık: f/4", lines)
        self.assertIn("Enstantane: 1/500 s", lines)
        self.assertIn("ISO: 800", lines)

    def test_format_af_lines(self) -> None:
        result = AnalysisResult(
            identity=FileIdentity(path=Path("/tmp/test.jpg"), size_bytes=1234, sha256="abc"),
            decision=Decision.SELECTED,
            hints=SubjectHints(category=PhotoCategory.BIRD, subject_label="bird"),
        )
        result.extras["af_point_label"] = "G9"
        result.extras["af_point_index"] = 68
        result.extras["af_detection_method"] = "Phase Detect"
        result.extras["af_area_mode"] = "Single Area"
        result.extras["af_info_version"] = "0100"

        lines = format_af_lines(result)

        self.assertIn("AF noktası: G9", lines)
        self.assertIn("AF indeks: 68", lines)
        self.assertIn("Algılama yöntemi: Phase Detect", lines)
        self.assertIn("AF alan modu: Single Area", lines)
        self.assertIn("AF Info2 sürümü: 0100", lines)

    def test_load_preview_frame_builds_focus_point(self) -> None:
        import tempfile
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "edge.jpg"
            image = Image.new("RGB", (240, 160), "gray")
            draw = ImageDraw.Draw(image)
            for x in range(0, 120, 8):
                draw.line((x, 0, x, 159), fill="black", width=2)
            image.save(path, quality=95)

            frame = load_preview_frame(path, max_size=(320, 240))

            self.assertIsNotNone(frame.image)
            self.assertIsNotNone(frame.focus_point)
            self.assertGreaterEqual(frame.focus_point.score if frame.focus_point is not None else 0.0, 0.0)
            self.assertLessEqual(frame.focus_point.score if frame.focus_point is not None else 1.0, 1.0)
            self.assertGreater(frame.focus_point.radius if frame.focus_point is not None else 0.0, 0.0)

    def test_nikon_d5_focus_point_mapping_uses_central_af_area(self) -> None:
        point = focus_point_from_nikon_label("I9", (1600, 1068), camera_model="NIKON D5")

        self.assertIsNotNone(point)
        assert point is not None
        self.assertGreater(point.x, 900)
        self.assertLess(point.x, 1200)
        self.assertAlmostEqual(point.y, 534.0, delta=40.0)

    def test_focus_rects_expand_for_group_modes(self) -> None:
        rects = focus_rects_from_nikon_label(
            "G9",
            (1600, 1068),
            camera_model="NIKON D5",
            area_mode="Group Area (HL)",
        )

        self.assertGreaterEqual(len(rects), 1)
        self.assertTrue(any(rect.width > rect.height for rect in rects))


if __name__ == "__main__":
    unittest.main()
