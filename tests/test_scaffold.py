from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed database*")
warnings.simplefilter("ignore", ResourceWarning)

from firfoto.core.config import load_config
from firfoto.core.identification import compute_sha256
from firfoto.core.metadata import collect_basic_metadata, _extract_sony_focus_point
from firfoto.core.workflow import BatchOptions, run_batch
from firfoto.storage.sqlite import (
    add_tags_to_catalog,
    delete_tag_globally,
    load_latest_analysis_results,
    load_photo_feedback,
    load_tag_catalog,
    rename_tag_globally,
    save_photo_feedback,
)
from PIL import Image, ImageDraw
from firfoto.core.scanner import scan_photos


class ScaffoldTests(unittest.TestCase):
    def test_config_loads(self) -> None:
        config = load_config()
        self.assertIn("nef", config.scan.supported_extensions)
        self.assertIn("bird", config.analysis.categories)

    def test_scan_finds_supported_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.NEF").write_bytes(b"nef")
            (root / ".hidden.NEF").write_bytes(b"nef")
            (root / "b.txt").write_text("ignore", encoding="utf-8")

            config = load_config()
            result = scan_photos(root, recursive=False, config=config)

            self.assertEqual(len(result.files), 1)
            self.assertEqual(result.files[0].path.name, "a.NEF")

    def test_scan_ignores_dotfiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".hidden.jpg").write_bytes(b"jpg")
            (root / "visible.jpg").write_bytes(b"jpg")

            config = load_config()
            result = scan_photos(root, recursive=False, config=config)

            self.assertEqual([item.path.name for item in result.files], ["visible.jpg"])

    def test_cli_show_config(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "firfoto.cli", "show-config"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(SRC)},
        )
        self.assertIn("Default profile:", completed.stdout)

    def test_cli_metadata_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "camera.jpg"
            image = Image.new("RGB", (64, 64), "white")
            exif = image.getexif()
            exif[271] = "Nikon"
            exif[272] = "NIKON D5"
            image.save(path, quality=92, exif=exif.tobytes())

            completed = subprocess.run(
                [sys.executable, "-m", "firfoto.cli", "metadata", str(path), "--json"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(SRC)},
            )

            payload = completed.stdout
            self.assertIn('"path":', payload)
            self.assertIn('"camera":', payload)
            self.assertIn('"model": "NIKON D5"', payload)

    def test_cli_render_preview_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "camera.jpg"
            output_path = root / "preview.png"
            image = Image.new("RGB", (80, 60), "white")
            image.save(image_path, quality=92)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "firfoto.cli",
                    "render-preview",
                    str(image_path),
                    "--output",
                    str(output_path),
                    "--json",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(SRC)},
            )

            self.assertIn(str(output_path), completed.stdout)
            self.assertTrue(output_path.exists())

    def test_cli_render_preview_can_use_separate_metadata_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            render_path = root / "scene.jpg"
            metadata_path = root / "scene_meta.jpg"
            output_path = root / "preview.png"

            Image.new("RGB", (80, 60), "white").save(render_path, quality=92)
            exif_image = Image.new("RGB", (64, 64), "white")
            exif = exif_image.getexif()
            exif[271] = "Nikon"
            exif[272] = "NIKON D5"
            exif_image.save(metadata_path, quality=92, exif=exif.tobytes())

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "firfoto.cli",
                    "render-preview",
                    str(render_path),
                    "--metadata-source",
                    str(metadata_path),
                    "--output",
                    str(output_path),
                    "--json",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(SRC)},
            )

            self.assertIn(str(render_path), completed.stdout)
            self.assertIn(str(metadata_path), completed.stdout)
            self.assertTrue(output_path.exists())

    def test_cli_results_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "a.jpg"
            Image.new("RGB", (64, 64), "white").save(image_path)
            db_path = root / ".firfoto" / "analysis.sqlite3"

            run_batch(
                root,
                options=BatchOptions(
                    recursive=False,
                    include_hash=False,
                    db_path=db_path,
                    dry_run=False,
                    category="bird",
                ),
                config=load_config(),
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "firfoto.cli",
                    "results",
                    str(root),
                    "--db",
                    str(db_path),
                    "--json",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(SRC)},
            )

            self.assertIn('"loaded_count": 1', completed.stdout)
            self.assertIn('"decision":', completed.stdout)

    def test_cli_analyze_stream_emits_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            Image.new("RGB", (64, 64), "white").save(root / "a.jpg")
            db_path = root / ".firfoto" / "analysis.sqlite3"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "firfoto.cli",
                    "analyze-stream",
                    str(root),
                    "--db",
                    str(db_path),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(SRC)},
            )

            self.assertIn('"event": "started"', completed.stdout)
            self.assertIn('"event": "progress"', completed.stdout)
            self.assertIn('"event": "completed"', completed.stdout)
            self.assertTrue(db_path.exists())

    def test_cli_feedback_roundtrip_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "a.jpg"
            Image.new("RGB", (64, 64), "white").save(image_path)
            db_path = root / ".firfoto" / "analysis.sqlite3"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "firfoto.cli",
                    "feedback-set",
                    str(root),
                    str(image_path),
                    "--db",
                    str(db_path),
                    "--decision",
                    "selected",
                    "--category",
                    "bird",
                    "--tag",
                    "hero",
                    "--tag",
                    "af-good",
                    "--json",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(SRC)},
            )
            self.assertIn('"decision_override": "selected"', completed.stdout)
            self.assertIn('"category_override": "bird"', completed.stdout)
            self.assertIn('"tags": [', completed.stdout)

            loaded = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "firfoto.cli",
                    "feedback-get",
                    str(root),
                    "--db",
                    str(db_path),
                    "--json",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(SRC)},
            )
            self.assertIn('"loaded_count": 1', loaded.stdout)
            self.assertIn('"decision_override": "selected"', loaded.stdout)
            self.assertIn('"hero"', loaded.stdout)

    def test_sha256_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.nef"
            path.write_bytes(b"abc123")

            self.assertEqual(
                compute_sha256(path),
                "6ca13d52ca70c883e0f0bb101e425a89e8624de51db2d2392593af6a84118090",
            )

    def test_analyze_writes_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "a.jpg"
            image = Image.new("RGB", (256, 256), "white")
            draw = ImageDraw.Draw(image)
            for i in range(0, 256, 16):
                draw.line((0, i, 255, i), fill="black", width=1)
                draw.line((i, 0, i, 255), fill="black", width=1)
            image.save(image_path, quality=95)
            db_path = root / "firfoto.sqlite3"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "firfoto.cli",
                    "analyze",
                    str(root),
                    "--db",
                    str(db_path),
                    "--recursive",
                    "--category",
                    "bird",
                    "--json",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(SRC)},
            )
            self.assertIn('"analyzed_count": 1', completed.stdout)
            self.assertIn('"sharpness":', completed.stdout)
            with sqlite3.connect(db_path) as connection:
                row_count = connection.execute("SELECT COUNT(*) FROM photo_analysis").fetchone()[0]
            self.assertEqual(row_count, 1)

    def test_run_batch_reports_progress_and_can_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            Image.new("RGB", (64, 64), "white").save(root / "a.jpg")
            Image.new("RGB", (64, 64), "white").save(root / "b.jpg")

            progress_events: list[tuple[int, int, str]] = []

            result = run_batch(
                root,
                options=BatchOptions(recursive=False, include_hash=False, dry_run=True),
                config=load_config(),
                progress_callback=lambda current, total, path: progress_events.append((current, total, path.name)),
                should_cancel=lambda: len(progress_events) >= 1,
            )

            self.assertTrue(result.canceled)
            self.assertEqual(len(result.results), 1)
            self.assertEqual(progress_events[0], (1, 2, "a.jpg"))

    def test_load_latest_analysis_results_returns_latest_per_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "a.jpg"
            Image.new("RGB", (64, 64), "white").save(image_path)
            db_path = root / ".firfoto" / "analysis.sqlite3"

            first = run_batch(
                root,
                options=BatchOptions(
                    recursive=False,
                    include_hash=False,
                    db_path=db_path,
                    dry_run=False,
                    category="general",
                ),
                config=load_config(),
            )
            second = run_batch(
                root,
                options=BatchOptions(
                    recursive=False,
                    include_hash=False,
                    db_path=db_path,
                    dry_run=False,
                    category="bird",
                ),
                config=load_config(),
            )

            loaded = load_latest_analysis_results(db_path, folder=root)

            self.assertEqual(len(first.results), 1)
            self.assertEqual(len(second.results), 1)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].identity.path, image_path)
            self.assertEqual(loaded[0].hints.category.value, "bird")

    def test_photo_feedback_roundtrip_returns_latest_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "a.jpg"
            Image.new("RGB", (64, 64), "white").save(image_path)
            db_path = root / ".firfoto" / "analysis.sqlite3"

            save_photo_feedback(
                db_path,
                path=image_path,
                decision_override="candidate",
                category_override="general",
                tags=["keep"],
            )
            save_photo_feedback(
                db_path,
                path=image_path,
                decision_override="selected",
                category_override="bird",
                tags=["hero", "af-good"],
            )

            loaded = load_photo_feedback(db_path, folder=root)

            self.assertEqual(len(loaded), 1)
            self.assertEqual(Path(str(loaded[0]["path"])), image_path)
            self.assertEqual(loaded[0]["decision_override"], "selected")
            self.assertEqual(loaded[0]["category_override"], "bird")
            self.assertEqual(loaded[0]["tags"], ["hero", "af-good"])

    def test_tag_catalog_can_add_rename_and_delete_globally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "a.jpg"
            Image.new("RGB", (64, 64), "white").save(image_path)
            db_path = root / ".firfoto" / "analysis.sqlite3"

            save_photo_feedback(
                db_path,
                path=image_path,
                tags=["hero", "client-pick"],
            )
            catalog = add_tags_to_catalog(db_path, ["portfolio"])
            self.assertIn("client-pick", catalog)
            self.assertIn("portfolio", catalog)

            renamed = rename_tag_globally(db_path, "client-pick", "client-final")
            self.assertIn("client-final", renamed)
            self.assertNotIn("client-pick", renamed)

            feedback = load_photo_feedback(db_path, folder=root)
            self.assertEqual(feedback[0]["tags"], ["client-final", "hero"])

            deleted = delete_tag_globally(db_path, "hero")
            self.assertNotIn("hero", deleted)
            self.assertIn("client-final", load_tag_catalog(db_path))

            feedback_after_delete = load_photo_feedback(db_path, folder=root)
            self.assertEqual(feedback_after_delete[0]["tags"], ["client-final"])

    def test_metadata_reads_exif(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "camera.jpg"
            image = Image.new("RGB", (64, 64), "white")
            exif = image.getexif()
            exif[271] = "Nikon"
            exif[272] = "NIKON D5"
            exif[42035] = "Nikon"
            exif[42036] = "AF-S NIKKOR 70-200mm f/2.8E FL ED VR"
            exif[37386] = (200, 1)
            exif[33437] = (28, 10)
            image.save(path, quality=92, exif=exif.tobytes())

            metadata = collect_basic_metadata(path)

            self.assertEqual(metadata.camera.maker, "Nikon")
            self.assertEqual(metadata.camera.model, "NIKON D5")
            self.assertEqual(metadata.lens.model, "AF-S NIKKOR 70-200mm f/2.8E FL ED VR")

    def test_metadata_reads_nikon_af_point(self) -> None:
        nef_path = Path("/Volumes/SAMSUNG/DCIM/116SCPD5/ND5_2878.NEF")
        if not nef_path.exists():
            self.skipTest(f"Sample NEF not available: {nef_path}")

        metadata = collect_basic_metadata(nef_path)

        self.assertEqual(metadata.camera.model, "NIKON D5")
        self.assertEqual(metadata.af_point_label, "G9")
        self.assertEqual(metadata.af_detection_method, "Phase Detect")

    def test_metadata_infers_nikon_lens_fallback(self) -> None:
        nef_path = Path("/Users/melihfidan/DCIM/116SCPD5/ND5_3263.NEF")
        if not nef_path.exists():
            self.skipTest(f"Sample NEF not available: {nef_path}")

        metadata = collect_basic_metadata(nef_path)

        self.assertIsNotNone(metadata.lens.model)
        self.assertTrue("mm" in metadata.lens.model or "LensType" in metadata.lens.model)

    def test_metadata_reads_subject_area_as_focus_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "canon_like.jpg"
            image = Image.new("RGB", (640, 480), "white")
            exif = image.getexif()
            exif[271] = "Canon"
            exif[272] = "Canon EOS R5"
            exif[37396] = (320, 240, 120, 80)
            image.save(path, quality=92, exif=exif.tobytes())

            metadata = collect_basic_metadata(path)

            self.assertEqual(metadata.camera.maker, "Canon")
            self.assertEqual(metadata.af_point_label, "Active area")
            self.assertEqual(metadata.af_area_x, 320)
            self.assertEqual(metadata.af_area_y, 240)

    def test_extract_sony_focus_point_skips_manual_focus(self) -> None:
        label, detection_method, area_mode = _extract_sony_focus_point({"MakerNote FocusMode": "Manual"})

        self.assertIsNone(label)
        self.assertEqual(detection_method, "Manual")
        self.assertIsNone(area_mode)

    def test_cli_metadata_json_includes_subject_area(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sony_like.jpg"
            image = Image.new("RGB", (640, 480), "white")
            exif = image.getexif()
            exif[271] = "SONY"
            exif[272] = "ILCE-1"
            exif[37396] = (200, 150, 90, 90)
            image.save(path, quality=92, exif=exif.tobytes())

            completed = subprocess.run(
                [sys.executable, "-m", "firfoto.cli", "metadata", str(path), "--json"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(SRC)},
            )

            self.assertIn('"area_x": 200', completed.stdout)
            self.assertIn('"area_width": 90', completed.stdout)


if __name__ == "__main__":
    unittest.main()
