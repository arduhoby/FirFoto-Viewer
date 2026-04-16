from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QHeaderView
from PySide6.QtWidgets import QApplication

from firfoto.core.config import load_config
from firfoto.core.models import AnalysisMetrics, AnalysisResult, Decision, FileIdentity
from firfoto.core.workflow import BatchOptions, run_batch
from firfoto.gui.qt_app import FirfotoPreviewWindow


class QtGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_analyze_stays_manual_until_folder_exists(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        window.folder_edit.setText("")
        window._sync_analyze_state()
        self.assertFalse(window.analyze_button.isEnabled())

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image = Image.new("RGB", (64, 64), "white")
            image.save(folder / "sample.jpg")

            window.folder_edit.setText(str(folder))
            window._sync_analyze_state()
            self.assertTrue(window.analyze_button.isEnabled())

    def test_browse_only_sets_folder_without_loading(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (64, 64), "white").save(folder / "sample.jpg")

            with patch("firfoto.gui.qt_app.QFileDialog.getExistingDirectory", return_value=str(folder)):
                window._browse_folder()

            self.assertEqual(window.folder_edit.text(), str(folder))
            self.assertEqual(window._folder_files, [])
            self.assertIn("Click Analyze", window.status_label.text())

    def test_folder_loading_supports_navigation(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (64, 64), "white").save(folder / "a.jpg")
            Image.new("RGB", (64, 64), "white").save(folder / "b.jpg")

            window.recursive_check.setChecked(False)
            window.folder_edit.setText(str(folder))
            window._load_folder_files(folder)

            self.assertEqual(len(window._folder_files), 2)
            self.assertEqual(window._current_index, 0)

            window._navigate(1)
            self.assertEqual(window._current_index, 1)

    def test_zoom_controls_resize_preview(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (320, 200), "white").save(folder / "a.jpg")

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)

            self.assertIsNotNone(window._preview_pixmap)
            base_width = window._preview_pixmap.width()
            window.zoom_slider.setValue(150)
            self.assertEqual(window.zoom_value_label.text(), "150%")
            self.assertIsNotNone(window._preview_pixmap)
            self.assertGreater(window._preview_pixmap.width(), base_width)

    def test_ctrl_wheel_zoom_changes_preview(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (320, 200), "white").save(folder / "a.jpg")

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)

            start_zoom = window.zoom_slider.value()
            wheel = QWheelEvent(
                QPointF(1, 1),
                QPointF(1, 1),
                QPoint(0, 0),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.ControlModifier,
                Qt.ScrollPhase.ScrollUpdate,
                False,
            )
            handled = window.eventFilter(window.preview_scroll.viewport(), wheel)

            self.assertTrue(handled)
            self.assertGreater(window.zoom_slider.value(), start_zoom)

    def test_exposure_controls_adjust_preview(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (160, 120), (80, 80, 80)).save(folder / "a.jpg")

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)

            self.assertIsNotNone(window._preview_pixmap)
            base_color = window._preview_pixmap.toImage().pixelColor(10, 10)

            window.exposure_slider.setValue(150)
            self.assertEqual(window.exposure_value_label.text(), "150%")
            bright_color = window._preview_pixmap.toImage().pixelColor(10, 10)

            self.assertGreater(bright_color.red(), base_color.red())
            self.assertGreater(bright_color.green(), base_color.green())
            self.assertGreater(bright_color.blue(), base_color.blue())

    def test_fit_preview_resets_zoom_and_exposure(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (160, 120), (80, 80, 80)).save(folder / "a.jpg")

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)

            window.zoom_slider.setValue(180)
            window.exposure_slider.setValue(140)
            window._fit_preview()

            self.assertEqual(window.zoom_value_label.text(), "100%")
            self.assertEqual(window.exposure_value_label.text(), "100%")

    def test_details_panel_can_toggle(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        self.assertTrue(window.details_toggle.isChecked())
        details_widget = window.preview_splitter.widget(1)
        self.assertIsNotNone(details_widget)
        self.assertFalse(details_widget.isHidden())

        window.details_toggle.setChecked(False)
        self.assertTrue(details_widget.isHidden())

        window.details_toggle.setChecked(True)
        self.assertFalse(details_widget.isHidden())

    def test_focus_toggles_start_hidden_and_can_enable_overlays(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        self.assertFalse(window.camera_af_toggle.isChecked())
        self.assertFalse(window.sharp_guess_toggle.isChecked())

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (160, 120), "white").save(folder / "a.jpg")

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)
            self.assertFalse(window._show_camera_af)
            self.assertFalse(window._show_sharp_guess)
            self.assertEqual(window._camera_af_rects, [])

            window.sharp_guess_toggle.setChecked(True)
            self.assertTrue(window._show_sharp_guess)
            self.assertIsNotNone(window._sharpness_focus_point)

    def test_thumbnail_strip_tracks_current_item(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (96, 96), "red").save(folder / "a.jpg")
            Image.new("RGB", (96, 96), "green").save(folder / "b.jpg")
            Image.new("RGB", (96, 96), "blue").save(folder / "c.jpg")

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)

            self.assertEqual(len(window.thumbnail_buttons), 3)
            window.thumbnail_buttons[-1].click()
            self.assertEqual(window._current_index, 2)
            self.assertIn("3/3", window.current_file_label.text())

    def test_thumbnail_strip_matches_file_count(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            for index in range(8):
                Image.new("RGB", (96, 96), "white").save(folder / f"{index:02d}.jpg")

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)

            self.assertEqual(len(window.thumbnail_buttons), len(window._folder_files))

    def test_selected_result_shows_color_summary(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            Image.new("RGB", (96, 96), "white").save(image_path)

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)
            window._result_by_path[str(image_path)] = AnalysisResult(
                identity=FileIdentity(path=image_path, size_bytes=image_path.stat().st_size),
                metrics=AnalysisMetrics(overall_quality=0.91),
                decision=Decision.SELECTED,
            )
            window._rebuild_table()
            window._show_result(window._result_by_path[str(image_path)])

            self.assertIn("Selected", window.summary_label.text())
            self.assertGreater(window.table.item(0, 1).background().color().green(), window.table.item(0, 1).background().color().red())

    def test_basic_file_moves_path_to_bottom(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            Image.new("RGB", (96, 96), "white").save(image_path)

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)

            detail_text = window.details.toPlainText()
            self.assertIn("Dosya Yolu", detail_text)
            self.assertIn(str(image_path), detail_text)
            self.assertLess(detail_text.find("Analiz"), detail_text.find("Dosya Yolu"))

    def test_header_sort_orders_quality_column(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            a_path = folder / "a.jpg"
            b_path = folder / "b.jpg"
            Image.new("RGB", (96, 96), "white").save(a_path)
            Image.new("RGB", (96, 96), "white").save(b_path)

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)
            window._result_by_path = {
                str(a_path): AnalysisResult(
                    identity=FileIdentity(path=a_path, size_bytes=a_path.stat().st_size),
                    metrics=AnalysisMetrics(overall_quality=0.90),
                    decision=Decision.SELECTED,
                ),
                str(b_path): AnalysisResult(
                    identity=FileIdentity(path=b_path, size_bytes=b_path.stat().st_size),
                    metrics=AnalysisMetrics(overall_quality=0.40),
                    decision=Decision.CANDIDATE,
                ),
            }
            window._rebuild_table()

            window.table.sortItems(2, Qt.SortOrder.AscendingOrder)
            self.assertEqual(window.table.item(0, 0).text(), "b.jpg")

            window.table.sortItems(2, Qt.SortOrder.DescendingOrder)
            self.assertEqual(window.table.item(0, 0).text(), "a.jpg")

    def test_sorted_table_click_opens_matching_file(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            a_path = folder / "a.jpg"
            b_path = folder / "b.jpg"
            Image.new("RGB", (96, 96), "white").save(a_path)
            Image.new("RGB", (96, 96), "white").save(b_path)

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)
            window._result_by_path = {
                str(a_path): AnalysisResult(
                    identity=FileIdentity(path=a_path, size_bytes=a_path.stat().st_size),
                    metrics=AnalysisMetrics(overall_quality=0.90),
                    decision=Decision.SELECTED,
                ),
                str(b_path): AnalysisResult(
                    identity=FileIdentity(path=b_path, size_bytes=b_path.stat().st_size),
                    metrics=AnalysisMetrics(overall_quality=0.40),
                    decision=Decision.CANDIDATE,
                ),
            }
            window._rebuild_table()
            window.table.sortItems(2, Qt.SortOrder.AscendingOrder)

            window.table.selectRow(0)
            window._on_table_selection_changed()

            self.assertEqual(window.current_file_label.text().split()[-1], "b.jpg")

    def test_thumbnail_click_updates_detail_panel(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            a_path = folder / "a.jpg"
            b_path = folder / "b.jpg"
            Image.new("RGB", (96, 96), "white").save(a_path)
            Image.new("RGB", (96, 96), "black").save(b_path)

            window.recursive_check.setChecked(False)
            window._load_folder_files(folder)

            self.assertIn("a.jpg", window.details.toPlainText())
            window.thumbnail_buttons[-1].click()
            self.assertIn("b.jpg", window.details.toPlainText())

    def test_analysis_running_toggles_buttons(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            Image.new("RGB", (96, 96), "white").save(folder / "a.jpg")

            window.folder_edit.setText(str(folder))
            window._sync_analyze_state()
            self.assertTrue(window.analyze_button.isEnabled())
            self.assertFalse(window.cancel_button.isEnabled())

    def test_folder_load_restores_saved_results_from_sqlite(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            Image.new("RGB", (96, 96), "white").save(image_path)

            run_batch(
                folder,
                options=BatchOptions(
                    recursive=False,
                    include_hash=False,
                    db_path=folder / ".firfoto" / "analysis.sqlite3",
                    dry_run=False,
                    category="bird",
                ),
                config=config,
            )

            window.recursive_check.setChecked(False)
            window.folder_edit.setText(str(folder))
            window._load_folder_files(folder)

            self.assertIn(str(image_path), window._result_by_path)
            self.assertEqual(window.table.item(0, 1).text(), "candidate")
            self.assertIn("Loaded 1 saved analyses.", window.status_label.text())

            window._set_analysis_running(True)
            self.assertFalse(window.analyze_button.isEnabled())
            self.assertTrue(window.cancel_button.isEnabled())

            window._set_analysis_running(False)
            self.assertTrue(window.analyze_button.isEnabled())
            self.assertFalse(window.cancel_button.isEnabled())

    def test_table_hides_vertical_path_header(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        self.assertFalse(window.table.verticalHeader().isVisible())

    def test_table_and_preview_default_layout_is_balanced(self) -> None:
        config = load_config()
        window = FirfotoPreviewWindow(config=config)
        self.addCleanup(window.close)

        header = window.table.horizontalHeader()
        self.assertEqual(header.sectionResizeMode(0), QHeaderView.ResizeMode.Interactive)
        self.assertEqual(header.sectionResizeMode(1), QHeaderView.ResizeMode.Interactive)
        self.assertEqual(header.sectionResizeMode(2), QHeaderView.ResizeMode.Interactive)
        self.assertEqual(header.sectionResizeMode(3), QHeaderView.ResizeMode.Interactive)
        self.assertEqual(window.table.columnWidth(0), 200)
        self.assertEqual(window.thumbnail_scroll.maximumHeight(), 74)
        self.assertEqual(window.left_panel.maximumWidth(), 520)


if __name__ == "__main__":
    unittest.main()
