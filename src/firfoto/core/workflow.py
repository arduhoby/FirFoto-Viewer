"""Core batch workflow orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from firfoto.core.analyzer import analyze_identity
from firfoto.core.config import AppConfig, normalize_category_name
from firfoto.core.identification import build_identity_bundle
from firfoto.core.models import AnalysisResult, CameraIdentity, LensIdentity, PhotoCategory, SubjectHints
from firfoto.core.metadata import collect_basic_metadata, infer_category_from_path
from firfoto.core.scanner import scan_photos
from firfoto.storage.sqlite import initialize_database, insert_analysis_result


@dataclass(slots=True)
class BatchOptions:
    recursive: bool = False
    include_hash: bool = True
    db_path: Path | None = None
    category: str | None = "auto"
    subject_label: str | None = None
    focus_zone: str | None = None
    camera_maker: str | None = None
    camera_model: str | None = None
    lens_maker: str | None = None
    lens_model: str | None = None
    dry_run: bool = False
    extras: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class BatchRunResult:
    folder: Path
    recursive: bool
    results: list[AnalysisResult]
    canceled: bool = False

    @property
    def analyzed_count(self) -> int:
        return len(self.results)


def _build_subject_hints(options: BatchOptions) -> SubjectHints:
    category = options.category
    if category is None or category.strip().lower() == "auto":
        resolved_category = PhotoCategory.GENERAL
    else:
        resolved_category = normalize_category_name(category)
    return SubjectHints(
        category=resolved_category,
        subject_label=options.subject_label,
        focus_zone=options.focus_zone,
    )


def run_batch(
    folder: Path,
    *,
    options: BatchOptions,
    config: AppConfig,
    progress_callback: Callable[[int, int, Path], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> BatchRunResult:
    scan_result = scan_photos(folder, recursive=options.recursive, config=config)

    if options.db_path is not None and not options.dry_run:
        initialize_database(options.db_path)

    results: list[AnalysisResult] = []

    total_files = len(scan_result.files)
    canceled = False

    for index, item in enumerate(scan_result.files, start=1):
        if should_cancel is not None and should_cancel():
            canceled = True
            break
        if progress_callback is not None:
            progress_callback(index, total_files, item.path)
        metadata = collect_basic_metadata(item.path)
        category_override = options.category
        if category_override is None or category_override.strip().lower() == "auto":
            hints = SubjectHints(
                category=metadata.category_hint or infer_category_from_path(item.path),
                subject_label=options.subject_label,
                focus_zone=options.focus_zone,
            )
        else:
            hints = _build_subject_hints(options)
        bundle = build_identity_bundle(
            item.path,
            include_hash=options.include_hash,
            camera=CameraIdentity(
                maker=options.camera_maker or metadata.camera.maker,
                model=options.camera_model or metadata.camera.model,
                serial_number=metadata.camera.serial_number,
            ),
            lens=LensIdentity(
                maker=options.lens_maker or metadata.lens.maker,
                model=options.lens_model or metadata.lens.model,
                focal_length_mm=metadata.lens.focal_length_mm,
                aperture_f=metadata.lens.aperture_f,
            ),
            hints=hints,
        )
        result = analyze_identity(bundle.file_identity, bundle.hints, metadata=metadata)
        result.camera = bundle.camera
        result.lens = bundle.lens
        result.extras.setdefault("image_width", metadata.width)
        result.extras.setdefault("image_height", metadata.height)
        result.extras.setdefault("focal_length_mm", metadata.focal_length_mm or result.lens.focal_length_mm)
        result.extras.setdefault("aperture_f", metadata.aperture_f or result.lens.aperture_f)
        result.extras.setdefault("exposure_time_s", metadata.exposure_time_s)
        result.extras.setdefault("iso", metadata.iso)
        result.extras.setdefault("af_point_index", metadata.af_point_index)
        result.extras.setdefault("af_point_label", metadata.af_point_label)
        result.extras.setdefault("af_info_version", metadata.af_info_version)
        result.extras.setdefault("af_detection_method", metadata.af_detection_method)
        result.extras.setdefault("af_area_mode", metadata.af_area_mode)
        result.extras.setdefault("category_source", "path_hint" if (options.category is None or options.category.strip().lower() == "auto") else "manual")
        if metadata.notes:
            result.metrics.notes.extend(metadata.notes)
        result.extras.update(options.extras)
        results.append(result)

        if options.db_path is not None and not options.dry_run:
            insert_analysis_result(options.db_path, result)

    return BatchRunResult(
        folder=scan_result.folder,
        recursive=scan_result.recursive,
        results=results,
        canceled=canceled,
    )
