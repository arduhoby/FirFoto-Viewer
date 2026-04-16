"""Qt preview GUI for Firfoto."""

from __future__ import annotations

import os
import threading
import traceback
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QBrush, QImage, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from firfoto.core.config import AppConfig, load_config
from firfoto.core.metadata import BasicMetadata, collect_basic_metadata, infer_category_from_path
from firfoto.core.scanner import scan_photos
from firfoto.core.models import AnalysisResult, Decision
from firfoto.core.workflow import BatchOptions, run_batch
from firfoto.gui.formatters import (
    format_af_lines,
    format_basic_capture_lines,
    format_capture_lines,
    format_identity_lines,
    format_metric_lines,
    format_reason_lines,
)
from firfoto.gui.image_loader import FocusPoint, FocusRect, PreviewFrame, focus_rects_from_nikon_label, load_preview_frame
from firfoto.storage.sqlite import load_latest_analysis_results


SUPPORTED_PREVIEW_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(slots=True)
class QtSelection:
    folder: Path | None = None
    recursive: bool = True
    category: str = "auto"


class AnalysisSignals(QObject):
    finished = Signal(object)
    cancelled = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)


class AnalysisWorker(QRunnable):
    def __init__(self, folder: Path, options: BatchOptions, config: AppConfig) -> None:
        super().__init__()
        self.folder = folder
        self.options = options
        self.config = config
        self.signals = AnalysisSignals()
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:  # pragma: no cover - threaded GUI path
        try:
            result = run_batch(
                self.folder,
                options=self.options,
                config=self.config,
                progress_callback=lambda current, total, path: self.signals.progress.emit(current, total, str(path)),
                should_cancel=self._cancel_event.is_set,
            )
            if result.canceled:
                self.signals.cancelled.emit(result)
            else:
                self.signals.finished.emit(result)
        except Exception:
            self.signals.failed.emit(traceback.format_exc())


class FirfotoPreviewWindow(QMainWindow):
    _PATH_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, config: AppConfig, initial_folder: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Firfoto Preview")
        self.resize(1400, 860)
        self.config = config
        self.selection = QtSelection(folder=initial_folder)
        self.thread_pool = QThreadPool.globalInstance()
        self._active_worker: AnalysisWorker | None = None
        self._analysis_running: bool = False
        self._shortcuts: list[QShortcut] = []
        self._folder_files: list[Path] = []
        self._current_index: int = -1
        self._results: list[AnalysisResult] = []
        self._result_by_path: dict[str, AnalysisResult] = {}
        self._metadata_cache: dict[str, BasicMetadata] = {}
        self._preview_frame: PreviewFrame | None = None
        self._preview_pixmap: QPixmap | None = None
        self._sharpness_focus_point: FocusPoint | None = None
        self._camera_af_rects: list[FocusRect] = []
        self._thumbnail_cache: dict[str, QPixmap] = {}
        self._thumbnail_button_by_path: dict[str, QToolButton] = {}
        self._thumbnail_load_queue: deque[Path] = deque()
        self.thumbnail_buttons: list[QToolButton] = []
        self._thumbnail_timer = QTimer(self)
        self._thumbnail_timer.setSingleShot(False)
        self._thumbnail_timer.setInterval(0)
        self._zoom_percent: int = 100
        self._exposure_percent: int = 100
        self._show_camera_af: bool = False
        self._show_sharp_guess: bool = False
        self._layout_initialized: bool = False
        self._db_path: Path | None = None
        self._build_ui()
        self._connect_signals()
        self._connect_shortcuts()
        if initial_folder is not None:
            self.folder_edit.setText(str(initial_folder))
            self._load_folder_files(initial_folder)
        self._sync_analyze_state()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        root.addWidget(controls)

        primary_bar = QHBoxLayout()
        controls_layout.addLayout(primary_bar)
        primary_bar.addWidget(QLabel("Folder"))
        self.folder_edit = QLineEdit()
        primary_bar.addWidget(self.folder_edit, 1)
        self.browse_button = QPushButton("Browse")
        primary_bar.addWidget(self.browse_button)
        self.analyze_button = QPushButton("Analyze")
        primary_bar.addWidget(self.analyze_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        primary_bar.addWidget(self.cancel_button)
        self.recursive_check = QCheckBox("Recursive")
        self.recursive_check.setChecked(True)
        primary_bar.addWidget(self.recursive_check)
        primary_bar.addWidget(QLabel("Category"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(["auto", "general", "bird", "wildlife", "portrait", "landscape", "sky", "aerial", "product", "macro"])
        primary_bar.addWidget(self.category_combo)
        self.prev_button = QPushButton("Prev")
        self.prev_button.setToolTip("Previous file")
        primary_bar.addWidget(self.prev_button)
        self.next_button = QPushButton("Next")
        self.next_button.setToolTip("Next file")
        primary_bar.addWidget(self.next_button)

        secondary_bar = QHBoxLayout()
        controls_layout.addLayout(secondary_bar)
        self.camera_af_toggle = QCheckBox("Camera AF")
        self.camera_af_toggle.setChecked(False)
        secondary_bar.addWidget(self.camera_af_toggle)
        self.sharp_guess_toggle = QCheckBox("Sharp guess")
        self.sharp_guess_toggle.setChecked(False)
        secondary_bar.addWidget(self.sharp_guess_toggle)
        self.details_toggle = QPushButton("Details")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setChecked(True)
        secondary_bar.addWidget(self.details_toggle)
        secondary_bar.addWidget(QLabel("Zoom"))
        self.zoom_out_button = QPushButton("-")
        self.zoom_out_button.setFixedWidth(28)
        secondary_bar.addWidget(self.zoom_out_button)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(50, 300)
        self.zoom_slider.setValue(self._zoom_percent)
        self.zoom_slider.setFixedWidth(140)
        secondary_bar.addWidget(self.zoom_slider)
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setFixedWidth(28)
        secondary_bar.addWidget(self.zoom_in_button)
        self.fit_button = QPushButton("Fit")
        secondary_bar.addWidget(self.fit_button)
        self.zoom_value_label = QLabel("100%")
        self.zoom_value_label.setMinimumWidth(48)
        secondary_bar.addWidget(self.zoom_value_label)
        secondary_bar.addWidget(QLabel("Exposure (EV)"))
        self.exposure_out_button = QPushButton("-")
        self.exposure_out_button.setFixedWidth(28)
        secondary_bar.addWidget(self.exposure_out_button)
        self.exposure_slider = QSlider(Qt.Orientation.Horizontal)
        self.exposure_slider.setRange(50, 180)
        self.exposure_slider.setValue(self._exposure_percent)
        self.exposure_slider.setFixedWidth(140)
        secondary_bar.addWidget(self.exposure_slider)
        self.exposure_in_button = QPushButton("+")
        self.exposure_in_button.setFixedWidth(28)
        secondary_bar.addWidget(self.exposure_in_button)
        self.exposure_value_label = QLabel("100%")
        self.exposure_value_label.setMinimumWidth(48)
        secondary_bar.addWidget(self.exposure_value_label)
        secondary_bar.addStretch(1)

        self.main_splitter = QSplitter()
        root.addWidget(self.main_splitter, 1)

        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(300)
        self.left_panel.setMaximumWidth(520)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["File", "Decision", "Quality", "Category"])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 100)
        left_layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.count_label = QLabel("0 items")
        self.current_file_label = QLabel("No file selected.")
        self.current_file_label.setMinimumWidth(220)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedWidth(220)
        self.status_label = QLabel("Choose a folder to start.")
        footer.addWidget(self.count_label)
        footer.addStretch(1)
        footer.addWidget(self.current_file_label)
        footer.addWidget(self.progress_bar)
        footer.addStretch(1)
        footer.addWidget(self.status_label)
        left_layout.addLayout(footer)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.thumbnail_scroll = QScrollArea()
        self.thumbnail_scroll.setWidgetResizable(True)
        self.thumbnail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.thumbnail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbnail_scroll.setFixedHeight(74)
        self.thumbnail_scroll.setStyleSheet("QScrollArea { border: 1px solid #444; background: #0d0d0d; }")
        self.thumbnail_host = QWidget()
        self.thumbnail_layout = QHBoxLayout(self.thumbnail_host)
        self.thumbnail_layout.setContentsMargins(6, 3, 6, 3)
        self.thumbnail_layout.setSpacing(6)
        self.thumbnail_layout.addStretch(1)
        self.thumbnail_scroll.setWidget(self.thumbnail_host)
        right_layout.addWidget(self.thumbnail_scroll, 0)

        self.preview_splitter = QSplitter(Qt.Orientation.Vertical)
        self.preview_splitter.setChildrenCollapsible(True)

        preview_host = QWidget()
        preview_host_layout = QVBoxLayout(preview_host)
        preview_host_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.setStyleSheet("QScrollArea { border: 1px solid #444; background: #111; }")
        self.preview_label = QLabel("Preview will appear here")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("QLabel { border: none; background: transparent; color: #bbb; }")
        self.preview_label.setToolTip("Camera AF ve Sharp guess işaretleri varsayılan kapalıdır; istersen kutuları açabilirsin.")
        self.preview_scroll.setWidget(self.preview_label)
        preview_host_layout.addWidget(self.preview_scroll, 1)

        details_host = QWidget()
        details_layout = QVBoxLayout(details_host)
        details_layout.setContentsMargins(0, 0, 0, 0)
        self.summary_label = QLabel("No analysis loaded")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "QLabel { border: 1px solid #444; border-radius: 8px; padding: 8px 10px; color: #eee; background: #222; }"
        )
        details_layout.addWidget(self.summary_label)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        details_layout.addWidget(self.details, 1)

        self.preview_splitter.addWidget(preview_host)
        self.preview_splitter.addWidget(details_host)
        self.preview_splitter.setStretchFactor(0, 5)
        self.preview_splitter.setStretchFactor(1, 1)
        self.preview_splitter.setSizes([820, 180])
        right_layout.addWidget(self.preview_splitter, 1)

        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(right)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 2)
        self._apply_main_splitter_sizes()

    def _connect_signals(self) -> None:
        self.browse_button.clicked.connect(self._browse_folder)
        self.analyze_button.clicked.connect(self._start_analysis)
        self.cancel_button.clicked.connect(self._cancel_analysis)
        self.prev_button.clicked.connect(lambda: self._navigate(-1))
        self.next_button.clicked.connect(lambda: self._navigate(1))
        self.folder_edit.textChanged.connect(self._sync_analyze_state)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.camera_af_toggle.toggled.connect(self._toggle_camera_af)
        self.sharp_guess_toggle.toggled.connect(self._toggle_sharp_guess)
        self.details_toggle.toggled.connect(self._toggle_details_panel)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        self.zoom_out_button.clicked.connect(lambda: self._change_zoom(-10))
        self.zoom_in_button.clicked.connect(lambda: self._change_zoom(10))
        self.fit_button.clicked.connect(self._fit_preview)
        self.exposure_slider.valueChanged.connect(self._on_exposure_changed)
        self.exposure_out_button.clicked.connect(lambda: self._change_exposure(-10))
        self.exposure_in_button.clicked.connect(lambda: self._change_exposure(10))
        self.preview_scroll.viewport().installEventFilter(self)
        self._thumbnail_timer.timeout.connect(self._process_thumbnail_queue)

    def _connect_shortcuts(self) -> None:
        for key, handler in (
            (Qt.Key.Key_Left, lambda: self._navigate(-1)),
            (Qt.Key.Key_Right, lambda: self._navigate(1)),
            (Qt.Key.Key_Home, lambda: self._navigate_to(0)),
            (Qt.Key.Key_End, lambda: self._navigate_to(len(self._folder_files) - 1)),
            (Qt.Key.Key_F, self._fit_preview),
            (Qt.Key.Key_D, lambda: self.details_toggle.setChecked(not self.details_toggle.isChecked())),
            (Qt.Key.Key_M, lambda: self.camera_af_toggle.setChecked(not self.camera_af_toggle.isChecked())),
            (Qt.Key.Key_Plus, lambda: self._change_zoom(10)),
            (Qt.Key.Key_Minus, lambda: self._change_zoom(-10)),
            (Qt.Key.Key_BracketLeft, lambda: self._change_exposure(-10)),
            (Qt.Key.Key_BracketRight, lambda: self._change_exposure(10)),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def _browse_folder(self) -> None:
        self._thumbnail_timer.stop()
        self._thumbnail_load_queue.clear()
        chosen = QFileDialog.getExistingDirectory(self, "Select photo folder")
        if not chosen:
            return
        self.folder_edit.setText(chosen)
        self.status_label.setText("Folder selected. Click Analyze to load and analyze.")
        self._sync_analyze_state()

    def _sync_analyze_state(self) -> None:
        folder = Path(self.folder_edit.text().strip()).expanduser() if self.folder_edit.text().strip() else None
        enabled = bool(folder and folder.is_dir()) and not self._analysis_running
        self.analyze_button.setEnabled(enabled)
        self.cancel_button.setEnabled(self._analysis_running)

    def _set_analysis_running(self, running: bool) -> None:
        self._analysis_running = running
        if not running:
            self._active_worker = None
        self._sync_analyze_state()

    def _load_folder_files(self, folder: Path) -> None:
        if not folder.exists() or not folder.is_dir():
            self._folder_files = []
            self._current_index = -1
            self._results = []
            self._result_by_path = {}
            self._metadata_cache = {}
            self._thumbnail_cache = {}
            self._clear_results()
            self.current_file_label.setText("No file selected.")
            self.status_label.setText("Folder not found.")
            self.count_label.setText("0 files")
            return

        scan_result = scan_photos(folder, recursive=self.recursive_check.isChecked(), config=self.config)
        self._db_path = self._default_db_path_for_folder(folder)
        self._folder_files = [item.path for item in scan_result.files]
        self._current_index = 0 if self._folder_files else -1
        self._results = self._load_persisted_results(folder)
        self._result_by_path = {str(item.identity.path): item for item in self._results}
        self._metadata_cache = {}
        self._thumbnail_cache = {}
        self._rebuild_table()
        self._rebuild_thumbnail_strip()
        self.count_label.setText(f"{len(self._folder_files)} files")
        if self._folder_files:
            self._select_current_row()
            self._show_current_file()
            if self._results:
                self.status_label.setText(f"Loaded {len(self._results)} saved analyses.")
            else:
                self.status_label.setText("Folder loaded. Click Analyze.")
        else:
            self._clear_results()
            self.current_file_label.setText("No file selected.")
            self.status_label.setText("No supported photo files found.")

    def _default_db_path_for_folder(self, folder: Path) -> Path:
        return folder / ".firfoto" / "analysis.sqlite3"

    def _load_persisted_results(self, folder: Path) -> list[AnalysisResult]:
        db_path = self._default_db_path_for_folder(folder)
        self._db_path = db_path
        return load_latest_analysis_results(db_path, folder=folder)

    def _start_analysis(self) -> None:
        if self._analysis_running:
            return
        folder_text = self.folder_edit.text().strip()
        if not folder_text:
            QMessageBox.warning(self, "Firfoto", "Please choose a folder first.")
            return

        folder = Path(folder_text).expanduser()
        if not folder.exists() or not folder.is_dir():
            QMessageBox.critical(self, "Firfoto", f"Folder not found: {folder}")
            return

        self.selection.folder = folder
        self.selection.recursive = self.recursive_check.isChecked()
        self.selection.category = self.category_combo.currentText().strip() or "auto"
        self._load_folder_files(folder)
        if not self._folder_files:
            return
        self._set_analysis_running(True)
        self.status_label.setText("Analyzing...")
        self.current_file_label.setText("Analyzing selected folder...")
        self.count_label.setText(f"{len(self._folder_files)} files")
        self.progress_bar.setRange(0, len(self._folder_files))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m")
        self._results = []
        self._result_by_path = {}
        self._rebuild_table()
        self._show_current_file()

        worker = AnalysisWorker(
            folder=folder,
            options=BatchOptions(
                recursive=self.selection.recursive,
                include_hash=False,
                db_path=self._db_path,
                category=self.selection.category,
                dry_run=False,
            ),
            config=self.config,
        )
        worker.signals.finished.connect(self._apply_results)
        worker.signals.cancelled.connect(self._analysis_cancelled)
        worker.signals.failed.connect(self._analysis_failed)
        worker.signals.progress.connect(self._update_progress)
        self._active_worker = worker
        self.thread_pool.start(worker)

    def _cancel_analysis(self) -> None:
        if self._active_worker is None:
            return
        self.status_label.setText("Cancelling...")
        self._active_worker.cancel()

    @Slot(object)
    def _apply_results(self, result: object) -> None:
        self._results = list(getattr(result, "results", []))
        self._result_by_path = {str(item.identity.path): item for item in self._results}
        self._rebuild_table()
        db_note = f" Saved to {self._db_path.name}." if self._db_path is not None else ""
        self.status_label.setText(f"Analyzed {len(self._results)} files.{db_note}")
        self.count_label.setText(f"{len(self._folder_files)} files")
        self.progress_bar.setValue(len(self._results))
        self._set_analysis_running(False)
        if self._folder_files:
            self._select_current_row()
            self._show_current_file()

    @Slot(object)
    def _analysis_cancelled(self, result: object) -> None:
        self._results = list(getattr(result, "results", []))
        self._result_by_path = {str(item.identity.path): item for item in self._results}
        self._rebuild_table()
        db_note = f" Partial results saved to {self._db_path.name}." if self._db_path is not None and self._results else ""
        self.status_label.setText(f"Cancelled after {len(self._results)} files.{db_note}")
        self.count_label.setText(f"{len(self._folder_files)} files")
        self.progress_bar.setValue(len(self._results))
        self._set_analysis_running(False)
        if self._folder_files:
            self._select_current_row()
            self._show_current_file()

    @Slot(str)
    def _analysis_failed(self, error_text: str) -> None:
        self.status_label.setText("Analysis failed.")
        QMessageBox.critical(self, "Firfoto", error_text)
        self._set_analysis_running(False)

    @Slot(int, int, str)
    def _update_progress(self, current: int, total: int, path_text: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(min(current, total))
        self.progress_bar.setFormat("%v / %m")
        self.current_file_label.setText(Path(path_text).name)

    def _clear_results(self) -> None:
        self.table.setRowCount(0)
        self.details.clear()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m")
        self.summary_label.setText("No analysis loaded")
        self.summary_label.setStyleSheet(
            "QLabel { border: 1px solid #444; border-radius: 8px; padding: 8px 10px; color: #eee; background: #222; }"
        )
        self.preview_label.setText("Preview will appear here")
        self.preview_label.setToolTip("Camera AF ve Sharp guess işaretleri varsayılan kapalıdır; istersen kutuları açabilirsin.")
        self._preview_pixmap = None
        self._current_index = -1
        self.current_file_label.setText("No file selected.")
        self._sharpness_focus_point = None
        self._camera_af_rects = []
        self._clear_thumbnail_strip()

    def _rebuild_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for path in self._folder_files:
            row = self.table.rowCount()
            self.table.insertRow(row)
            result = self._result_by_path.get(str(path))
            if result is None:
                quality = ""
                decision = ""
                category = infer_category_from_path(path).value
                quality_sort: float = -1.0
            else:
                quality = "n/a" if result.metrics.overall_quality is None else f"{result.metrics.overall_quality:.3f}"
                decision = result.decision.value
                category = result.hints.category.value
                quality_sort = -1.0 if result.metrics.overall_quality is None else float(result.metrics.overall_quality)
            items = [
                self._build_table_item(path.name, sort_value=path.name.lower(), path_value=str(path)),
                self._build_table_item(decision, sort_value=decision, path_value=str(path)),
                self._build_table_item(quality, sort_value=quality_sort, path_value=str(path)),
                self._build_table_item(category, sort_value=category, path_value=str(path)),
            ]
            for column, item in enumerate(items):
                if result is not None:
                    self._style_result_item(item, result.decision)
                self.table.setItem(row, column, item)
            self.table.setVerticalHeaderItem(row, QTableWidgetItem(str(path)))
        self.table.setSortingEnabled(True)

    def _on_table_selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        self._open_table_row(rows[0].row())

    @Slot(int, int)
    def _on_table_cell_clicked(self, row: int, _column: int) -> None:
        self._open_table_row(row)

    def _open_table_row(self, row: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        path_value = item.data(self._PATH_ROLE)
        if path_value is None:
            return
        self._open_path(Path(str(path_value)))

    def _navigate(self, delta: int) -> None:
        if not self._folder_files:
            return
        if self._current_index < 0:
            next_index = 0
        else:
            next_index = max(0, min(len(self._folder_files) - 1, self._current_index + delta))
        self._navigate_to(next_index)

    def _navigate_to(self, index: int) -> None:
        if not self._folder_files:
            return
        index = max(0, min(len(self._folder_files) - 1, index))
        self._open_path(self._folder_files[index])

    def _open_path(self, path: Path) -> None:
        try:
            self._current_index = self._folder_files.index(path)
        except ValueError:
            return
        self._select_current_row()
        self._show_current_file()

    def _select_current_row(self) -> None:
        if not (0 <= self._current_index < len(self._folder_files)):
            return
        current_path = str(self._folder_files[self._current_index])
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            if item.data(self._PATH_ROLE) == current_path:
                self.table.blockSignals(True)
                try:
                    self.table.selectRow(row)
                finally:
                    self.table.blockSignals(False)
                self.table.scrollToItem(item)
                break

    def _show_current_file(self) -> None:
        if not (0 <= self._current_index < len(self._folder_files)):
            return
        path = self._folder_files[self._current_index]
        result = self._result_by_path.get(str(path))
        if result is not None:
            self._show_result(result)
        else:
            self._show_basic_file(path)

        self.current_file_label.setText(f"{self._current_index + 1}/{len(self._folder_files)}  {path.name}")
        self._sync_thumbnail_selection()

    def _refresh_current_view(self) -> None:
        if 0 <= self._current_index < len(self._folder_files):
            self._show_current_file()

    def _clear_thumbnail_strip(self) -> None:
        self._thumbnail_timer.stop()
        self._thumbnail_load_queue.clear()
        while self.thumbnail_layout.count():
            item = self.thumbnail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.thumbnail_buttons = []
        self._thumbnail_button_by_path = {}

    def _thumbnail_placeholder(self) -> QIcon:
        pixmap = QPixmap(48, 34)
        pixmap.fill(QColor(32, 32, 32))
        painter = QPainter(pixmap)
        try:
            painter.setPen(QPen(QColor(90, 90, 90), 1))
            painter.drawRect(0, 0, pixmap.width() - 1, pixmap.height() - 1)
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "...")
        finally:
            painter.end()
        return QIcon(pixmap)

    def _thumbnail_pixmap_for_path(self, path: Path) -> QPixmap | None:
        cached = self._thumbnail_cache.get(str(path))
        if cached is not None:
            return cached
        try:
            frame = load_preview_frame(path, max_size=(320, 240))
        except Exception:
            return None
        if frame.image is None:
            return None
        pixmap = QPixmap.fromImage(frame.image).scaled(
            52,
            36,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumbnail_cache[str(path)] = pixmap
        return pixmap

    def _rebuild_thumbnail_strip(self) -> None:
        self._clear_thumbnail_strip()
        if not self._folder_files or self._current_index < 0:
            self.thumbnail_layout.addStretch(1)
            return

        placeholder_icon = self._thumbnail_placeholder()
        for index, path in enumerate(self._folder_files):
            thumb_button = QToolButton()
            thumb_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            thumb_button.setAutoRaise(True)
            thumb_button.setCheckable(True)
            thumb_button.setChecked(index == self._current_index)
            thumb_button.setIconSize(QSize(52, 36))
            thumb_button.setFixedSize(64, 56)
            thumb_button.setText(str(index + 1))
            thumb_button.setToolTip(str(path))
            thumb_button.setProperty("index", index)
            thumb_button.setIcon(placeholder_icon)
            thumb_button.clicked.connect(lambda _checked=False, idx=index: self._navigate_to(idx))
            self.thumbnail_layout.addWidget(thumb_button)
            self.thumbnail_buttons.append(thumb_button)
            self._thumbnail_button_by_path[str(path)] = thumb_button

        self.thumbnail_layout.addStretch(1)
        self._queue_thumbnail_loads()
        self._sync_thumbnail_selection()

    def _queue_thumbnail_loads(self) -> None:
        self._thumbnail_load_queue.clear()
        if not self._folder_files:
            return

        prioritized: list[Path] = []
        if 0 <= self._current_index < len(self._folder_files):
            prioritized.append(self._folder_files[self._current_index])
            for offset in range(1, len(self._folder_files)):
                left = self._current_index - offset
                right = self._current_index + offset
                if 0 <= left:
                    prioritized.append(self._folder_files[left])
                if right < len(self._folder_files):
                    prioritized.append(self._folder_files[right])
        else:
            prioritized = list(self._folder_files)

        for path in prioritized:
            if str(path) not in self._thumbnail_cache:
                self._thumbnail_load_queue.append(path)

        if self._thumbnail_load_queue:
            self._thumbnail_timer.start()

    def _process_thumbnail_queue(self) -> None:
        processed = 0
        while self._thumbnail_load_queue and processed < 2:
            path = self._thumbnail_load_queue.popleft()
            pixmap = self._thumbnail_pixmap_for_path(path)
            button = self._thumbnail_button_by_path.get(str(path))
            if pixmap is not None and button is not None:
                button.setIcon(QIcon(pixmap))
            processed += 1
        if not self._thumbnail_load_queue:
            self._thumbnail_timer.stop()

    def _sync_thumbnail_selection(self) -> None:
        current_path = str(self._folder_files[self._current_index]) if 0 <= self._current_index < len(self._folder_files) else None
        for index, path in enumerate(self._folder_files):
            button = self._thumbnail_button_by_path.get(str(path))
            if button is None:
                continue
            button.setChecked(index == self._current_index)
        if current_path is not None:
            button = self._thumbnail_button_by_path.get(current_path)
            if button is not None:
                self.thumbnail_scroll.ensureWidgetVisible(button, 24, 0)

    def _wheel_zoom_step(self, angle_delta_y: int) -> int:
        if angle_delta_y == 0:
            return 0
        step = 10
        if abs(angle_delta_y) >= 240:
            step = 20
        return step if angle_delta_y > 0 else -step

    def _apply_main_splitter_sizes(self) -> None:
        total_width = max(1, self.width())
        left_width = max(300, int(total_width * 0.33))
        right_width = max(500, total_width - left_width)
        self.main_splitter.setSizes([left_width, right_width])

    def _toggle_details_panel(self, visible: bool) -> None:
        details_widget = self.preview_splitter.widget(1)
        if details_widget is None:
            return
        details_widget.setVisible(visible)
        self.details_toggle.setText("Details" if visible else "Show details")
        if visible:
            self.preview_splitter.setSizes([820, 180])
        else:
            self.preview_splitter.setSizes([1, 0])
        self._refresh_preview_render()

    def _toggle_camera_af(self, visible: bool) -> None:
        self._show_camera_af = visible
        self._refresh_current_view()

    def _toggle_sharp_guess(self, visible: bool) -> None:
        self._show_sharp_guess = visible
        self._refresh_current_view()

    def _decision_palette(self, decision: Decision | None) -> tuple[str, str, QColor, QColor]:
        if decision == Decision.SELECTED or decision == Decision.BEST_OF_BURST:
            return "Selected", "En iyi kare", QColor(24, 122, 64), QColor(222, 255, 232)
        if decision == Decision.REJECTED:
            return "Rejected", "Elendi", QColor(150, 48, 56), QColor(255, 231, 232)
        return "Candidate", "Aday kare", QColor(164, 122, 20), QColor(255, 245, 220)

    def _summary_html(self, title: str, subtitle: str, decision: Decision | None) -> str:
        _, _, accent, tint = self._decision_palette(decision)
        accent_hex = accent.name()
        tint_hex = tint.name()
        return (
            f"<div style='background:{tint_hex}; border-left:4px solid {accent_hex}; padding:8px 10px;'>"
            f"<div style='font-size:16px; font-weight:700; color:#111;'>{title}</div>"
            f"<div style='font-size:12px; color:#333; margin-top:4px;'>{subtitle}</div>"
            "</div>"
        )

    def _style_result_item(self, item: QTableWidgetItem, decision: Decision) -> None:
        title, _, accent, tint = self._decision_palette(decision)
        item.setBackground(QBrush(tint))
        item.setForeground(QBrush(QColor(20, 20, 20)))
        if title:
            item.setToolTip(title)

    def _build_table_item(
        self,
        value: str,
        *,
        sort_value: float | str | None = None,
        path_value: str | None = None,
    ) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        item.setData(Qt.ItemDataRole.UserRole, value if sort_value is None else sort_value)
        if path_value is not None:
            item.setData(self._PATH_ROLE, path_value)
        return item

    def _on_zoom_changed(self, value: int) -> None:
        self._zoom_percent = max(50, min(300, value))
        self.zoom_value_label.setText(f"{self._zoom_percent}%")
        self._refresh_preview_render()

    def _change_zoom(self, delta: int) -> None:
        self.zoom_slider.setValue(self.zoom_slider.value() + delta)

    def _on_exposure_changed(self, value: int) -> None:
        self._exposure_percent = max(50, min(180, value))
        self.exposure_value_label.setText(f"{self._exposure_percent}%")
        self._refresh_preview_render()

    def _change_exposure(self, delta: int) -> None:
        self.exposure_slider.setValue(self.exposure_slider.value() + delta)

    def _fit_preview(self) -> None:
        self.zoom_slider.setValue(100)
        self.exposure_slider.setValue(100)
        self._refresh_preview_render()

    def _show_result(self, result: AnalysisResult) -> None:
        title, subtitle, _, _ = self._decision_palette(result.decision)
        score = result.metrics.overall_quality
        score_text = "n/a" if score is None else f"{score:.3f}"
        self.summary_label.setText(self._summary_html(title, f"{subtitle} · Skor: {score_text}", result.decision))
        metadata = self._metadata_cache.get(str(result.identity.path))
        if metadata is None:
            try:
                metadata = collect_basic_metadata(result.identity.path)
            except Exception:
                metadata = None
            if metadata is not None:
                self._metadata_cache[str(result.identity.path)] = metadata
        self._show_preview(result.identity.path, metadata=metadata)
        lines: list[str] = []
        lines.append("Kimlik")
        lines.extend(format_identity_lines(result))
        lines.append("")
        lines.append("Çekim Bilgileri")
        lines.extend(format_capture_lines(result))
        lines.append("")
        lines.append("AF / Netleme")
        lines.extend(format_af_lines(result))
        lines.append("")
        if (self._show_camera_af and self._camera_af_rects) or (self._show_sharp_guess and self._sharpness_focus_point is not None):
            lines.append("İşaretler")
            if self._show_camera_af and self._camera_af_rects:
                labels = ", ".join(rect.label for rect in self._camera_af_rects if rect.label) or "n/a"
                lines.append(f" - Kamera AF alanı: {labels} ({len(self._camera_af_rects)} kutu)")
            if self._show_sharp_guess and self._sharpness_focus_point is not None:
                lines.append(
                    f" - Tahmini sharp: {self._sharpness_focus_point.label or 'n/a'} "
                    f"({int(self._sharpness_focus_point.x)}, {int(self._sharpness_focus_point.y)}, yarıçap {int(self._sharpness_focus_point.radius)})"
                )
            lines.append("")
        lines.append("Kalite")
        lines.extend(format_metric_lines(result))
        lines.append("")
        lines.append("Nedenler")
        lines.extend(f" - {line}" for line in format_reason_lines(result))
        if self._show_camera_af and self._camera_af_rects:
            lines.append("")
            lines.append("Kamera AF alanı")
            for rect in self._camera_af_rects:
                lines.append(
                    f" - {rect.label or 'AF'} "
                    f"({int(rect.x)}, {int(rect.y)}, {int(rect.width)}x{int(rect.height)})"
                )
        if self._show_sharp_guess and self._sharpness_focus_point is not None:
            lines.append("")
            lines.append("Tahmini sharp noktası")
            lines.append(
                f" - {self._sharpness_focus_point.label or 'Sharp'} "
                f"({int(self._sharpness_focus_point.x)}, {int(self._sharpness_focus_point.y)}, yarıçap {int(self._sharpness_focus_point.radius)})"
            )
        extras = getattr(result, "extras", {})
        if extras:
            lines.append("")
            lines.append("Ek Bilgiler")
            for key, value in extras.items():
                lines.append(f" - {key}: {value}")
        self.details.setPlainText("\n".join(lines))

    def _show_basic_file(self, path: Path) -> None:
        self.summary_label.setText(
            self._summary_html(
                "Preview only",
                "Bu dosya henüz analiz edilmedi",
                None,
            )
        )
        metadata = self._metadata_cache.get(str(path))
        if metadata is None:
            try:
                metadata = collect_basic_metadata(path)
            except Exception:
                metadata = None
            if metadata is not None:
                self._metadata_cache[str(path)] = metadata
        self._show_preview(path, metadata=metadata)
        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = 0
        lines = [
            f"File: {path.name}",
            f"Size bytes: {size_bytes}",
            f"Kategori ipucu: {metadata.category_hint.value if metadata is not None else infer_category_from_path(path).value}",
            "",
        ]
        if metadata is not None:
            lines.extend(
                format_basic_capture_lines(
                    camera_maker=metadata.camera.maker,
                    camera_model=metadata.camera.model,
                    lens_maker=metadata.lens.maker,
                    lens_model=metadata.lens.model,
                    focal_length_mm=metadata.focal_length_mm,
                    aperture_f=metadata.aperture_f,
                    exposure_time_s=metadata.exposure_time_s,
                    iso=metadata.iso,
                    width=metadata.width,
                    height=metadata.height,
                )
            )
            lines.append("")
            lines.append("AF / Netleme")
            lines.append(f"AF noktası: {metadata.af_point_label or 'n/a'}")
            lines.append(
                f"AF algılama: {metadata.af_detection_method or 'n/a'}"
            )
            lines.append(
                f"AF alan modu: {metadata.af_area_mode or 'n/a'}"
            )
            if metadata.af_info_version:
                lines.append(f"AF Info2 sürümü: {metadata.af_info_version}")
            lines.append(f"Kamera AF görünür: {'evet' if self._show_camera_af else 'hayır'}")
            lines.append(f"Tahmini sharp görünür: {'evet' if self._show_sharp_guess else 'hayır'}")
            lines.append("")
            if self._show_camera_af and self._camera_af_rects:
                lines.append("Kamera AF alanı")
                for rect in self._camera_af_rects:
                    lines.append(
                        f" - {rect.label or 'AF'} "
                        f"({int(rect.x)}, {int(rect.y)}, {int(rect.width)}x{int(rect.height)})"
                    )
                lines.append("")
            if self._show_sharp_guess and self._sharpness_focus_point is not None:
                lines.append("Tahmini sharp noktası")
                lines.append(
                    f" - {self._sharpness_focus_point.label or 'Sharp'} "
                    f"({int(self._sharpness_focus_point.x)}, {int(self._sharpness_focus_point.y)}, yarıçap {int(self._sharpness_focus_point.radius)})"
                )
                lines.append("")
            if metadata.notes:
                lines.append("Meta notları")
                lines.extend(f" - {note}" for note in metadata.notes)
                lines.append("")
        lines.extend(
            [
            "Analiz",
            " - henüz analiz edilmedi",
            ]
        )
        lines.extend(
            [
                "",
                "Dosya Yolu",
                f" - {path}",
            ]
        )
        self.details.setPlainText("\n".join(lines))

    def _show_preview(self, path: Path, metadata: BasicMetadata | None = None) -> None:
        frame = load_preview_frame(path)
        self._preview_frame = frame
        if frame.image is None:
            self.preview_label.setText(frame.error or "Preview unavailable")
            self._preview_pixmap = None
            self._sharpness_focus_point = None
            self._camera_af_rects = []
            return
        self._sharpness_focus_point = frame.focus_point
        self._camera_af_rects = []
        if metadata is not None and metadata.af_point_label:
            self._camera_af_rects = focus_rects_from_nikon_label(
                metadata.af_point_label,
                (frame.image.width(), frame.image.height()),
                camera_model=metadata.camera.model,
                area_mode=metadata.af_area_mode,
            )
        self._refresh_preview_render()
        self.preview_label.setToolTip(self._preview_tooltip(metadata))

    def _refresh_preview_render(self) -> None:
        if self._preview_frame is None or self._preview_frame.image is None:
            return
        frame = self._preview_frame
        viewport = self.preview_scroll.viewport().size()
        if viewport.width() <= 0 or viewport.height() <= 0:
            viewport_width, viewport_height = 620, 420
        else:
            viewport_width, viewport_height = viewport.width(), viewport.height()
        fit_scale = max(viewport_width / max(1, frame.image.width()), viewport_height / max(1, frame.image.height()))
        fit_scale = max(0.05, fit_scale)
        scale = fit_scale * (self._zoom_percent / 100.0)
        pixmap = QPixmap.fromImage(frame.image)
        target_width = max(1, int(frame.image.width() * scale))
        target_height = max(1, int(frame.image.height() * scale))
        pixmap = pixmap.scaled(target_width, target_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        pixmap = self._apply_exposure_adjustment(pixmap)
        if self._show_camera_af or self._show_sharp_guess:
            self._draw_focus_overlay(
                pixmap,
                sharpness_focus_point=self._sharpness_focus_point,
                camera_focus_rects=self._camera_af_rects,
                source_width=frame.image.width(),
                source_height=frame.image.height(),
            )
        self._preview_pixmap = pixmap
        self.preview_label.setPixmap(pixmap)
        self.preview_label.setMinimumSize(pixmap.size())
        self.preview_label.resize(pixmap.size())

    def _apply_exposure_adjustment(self, pixmap: QPixmap) -> QPixmap:
        if self._exposure_percent == 100:
            return pixmap

        adjusted = QPixmap(pixmap)
        painter = QPainter(adjusted)
        try:
            if self._exposure_percent > 100:
                intensity = min(1.0, (self._exposure_percent - 100) / 80.0)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
                painter.fillRect(adjusted.rect(), QColor(255, 255, 255, int(120 * intensity)))
            else:
                intensity = min(1.0, (100 - self._exposure_percent) / 50.0)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
                painter.fillRect(adjusted.rect(), QColor(0, 0, 0, int(160 * intensity)))
        finally:
            painter.end()
        return adjusted

    def _draw_focus_overlay(
        self,
        pixmap: QPixmap,
        *,
        sharpness_focus_point: FocusPoint | None,
        camera_focus_rects: list[FocusRect],
        source_width: int,
        source_height: int,
    ) -> None:
        if source_width <= 0 or source_height <= 0:
            return

        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            if self._show_sharp_guess:
                self._draw_focus_marker(
                    painter,
                    sharpness_focus_point,
                    source_width=source_width,
                    source_height=source_height,
                    border=QColor(241, 196, 15, 235),
                    fill=QColor(241, 196, 15, 50),
                    label="Sharp",
                )
            if self._show_camera_af and camera_focus_rects:
                self._draw_camera_af_rects(
                    painter,
                    camera_focus_rects,
                    source_width=source_width,
                    source_height=source_height,
                )
            self._draw_overlay_legend(painter)
        finally:
            painter.end()

    def _draw_focus_marker(
        self,
        painter: QPainter,
        focus_point: FocusPoint | None,
        *,
        source_width: int,
        source_height: int,
        border: QColor,
        fill: QColor,
        label: str,
    ) -> None:
        if focus_point is None:
            return
        scale_x = painter.device().width() / source_width
        scale_y = painter.device().height() / source_height
        cx = focus_point.x * scale_x
        cy = focus_point.y * scale_y
        radius = max(7.0, focus_point.radius * ((scale_x + scale_y) / 2.0))
        painter.setPen(QPen(border, 2))
        painter.setBrush(fill)
        painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))
        painter.drawLine(int(cx - radius * 1.2), int(cy), int(cx + radius * 1.2), int(cy))
        painter.drawLine(int(cx), int(cy - radius * 1.2), int(cx), int(cy + radius * 1.2))
        painter.setPen(QColor(255, 255, 255, 230))
        display_label = focus_point.label or label
        painter.drawText(int(cx + radius + 4), int(cy - radius - 2), display_label)

    def _draw_camera_af_rects(
        self,
        painter: QPainter,
        rects: list[FocusRect],
        *,
        source_width: int,
        source_height: int,
    ) -> None:
        scale_x = painter.device().width() / source_width
        scale_y = painter.device().height() / source_height
        painter.setPen(QPen(QColor(225, 48, 48, 240), 2))
        painter.setBrush(QColor(225, 48, 48, 35))
        for rect in rects:
            painter.drawRect(
                int(rect.x * scale_x),
                int(rect.y * scale_y),
                max(6, int(rect.width * scale_x)),
                max(6, int(rect.height * scale_y)),
            )

    def _draw_overlay_legend(self, painter: QPainter) -> None:
        painter.save()
        try:
            box_width = 300
            box_height = 58
            painter.fillRect(10, 10, box_width, box_height, QColor(0, 0, 0, 140))
            painter.setPen(QColor(255, 255, 255, 235))
            painter.drawText(20, 28, self._overlay_label())
            painter.setPen(QColor(230, 230, 230, 220))
            painter.drawText(20, 44, self._overlay_description())
            painter.setPen(QColor(230, 230, 230, 220))
            painter.drawText(20, 56, "Kırmızı: kamera AF, sarı: tahmini sharp")
        finally:
            painter.restore()

    def _overlay_label(self) -> str:
        camera_text = "AF: açık" if self._show_camera_af else "AF: kapalı"
        sharp_text = "Sharp: açık" if self._show_sharp_guess else "Sharp: kapalı"
        return f"{camera_text} · {sharp_text}"

    def _overlay_description(self) -> str:
        return "Kamera AF metadata'dan, sharp ise tahmini ölçümden gelir"

    def _preview_tooltip(self, metadata: BasicMetadata | None) -> str:
        if not self._show_camera_af and not self._show_sharp_guess:
            return "AF ve sharp işaretleri kapalı. İstersen Camera AF veya Sharp guess kutularını aç. Ctrl+mouse wheel ile yakınlaştır."
        if self._show_camera_af and metadata is not None and metadata.af_point_label:
            return f"Kamera AF alanı gösteriliyor. Merkez nokta: {metadata.af_point_label}. Ctrl+mouse wheel ile yakınlaştır."
        if self._show_sharp_guess:
            return "Tahmini sharp noktası gösteriliyor. Ctrl+mouse wheel ile yakınlaştır."
        return "Ctrl+mouse wheel ile yakınlaştır."

    def eventFilter(self, watched, event) -> bool:  # pragma: no cover - GUI interaction
        if watched is self.preview_scroll.viewport() and event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta_y = event.angleDelta().y()
                step = self._wheel_zoom_step(delta_y)
                if step:
                    self._change_zoom(step)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # pragma: no cover - GUI interaction
        super().resizeEvent(event)
        self._apply_main_splitter_sizes()
        self._refresh_preview_render()


def launch_gui(config_path: Path | None = None, initial_folder: Path | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    config = load_config(config_path)
    window = FirfotoPreviewWindow(config=config, initial_folder=initial_folder)
    app._firfoto_window = window  # type: ignore[attr-defined]
    window.show()
    window.raise_()
    window.activateWindow()

    def _activate_window() -> None:
        window.showNormal()
        window.raise_()
        window.activateWindow()
        try:
            from AppKit import NSApp, NSApplicationActivationPolicyRegular

            NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)
            NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass

    QTimer.singleShot(0, _activate_window)
    auto_close_ms = os.environ.get("FIRFOTO_GUI_AUTOCLOSE_MS")
    if auto_close_ms:
        try:
            QTimer.singleShot(max(0, int(auto_close_ms)), app.quit)
        except ValueError:
            pass
    return app.exec()
