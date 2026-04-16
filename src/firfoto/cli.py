"""Command line interface for Firfoto."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from firfoto.core.config import AppConfig, load_config
from firfoto.core.workflow import BatchOptions, run_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="firfoto", description="Photo culling assistant")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional path to a TOML config file.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan a folder for supported photos.")
    scan_parser.add_argument("folder", type=Path, help="Folder to scan.")
    scan_parser.add_argument(
        "--recursive",
        action="store_true",
        help="Include subfolders.",
    )
    scan_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a folder and optionally store results in SQLite.")
    analyze_parser.add_argument("folder", type=Path, help="Folder to analyze.")
    analyze_parser.add_argument(
        "--recursive",
        action="store_true",
        help="Include subfolders.",
    )
    analyze_parser.add_argument(
        "--db",
        type=Path,
        default=Path("firfoto.sqlite3"),
        help="SQLite database path.",
    )
    analyze_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run analysis without writing to SQLite.",
    )
    analyze_parser.add_argument(
        "--category",
        type=str,
        default="auto",
        help="Initial subject/category hint.",
    )
    analyze_parser.add_argument("--subject-label", type=str, default=None, help="Optional subject label override.")
    analyze_parser.add_argument("--focus-zone", type=str, default=None, help="Optional focus zone hint.")
    analyze_parser.add_argument("--camera-maker", type=str, default=None, help="Camera maker override.")
    analyze_parser.add_argument("--camera-model", type=str, default=None, help="Camera model override.")
    analyze_parser.add_argument("--lens-maker", type=str, default=None, help="Lens maker override.")
    analyze_parser.add_argument("--lens-model", type=str, default=None, help="Lens model override.")
    analyze_parser.add_argument(
        "--no-hash",
        action="store_true",
        help="Skip sha256 hashing for faster dry-run workflows.",
    )
    analyze_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )

    config_parser = subparsers.add_parser("show-config", help="Print the loaded configuration.")
    config_parser.add_argument(
        "--json",
        action="store_true",
        help="Print configuration as JSON.",
    )

    gui_parser = subparsers.add_parser("gui", help="Open the simple preview GUI.")
    gui_parser.add_argument(
        "folder",
        nargs="?",
        type=Path,
        default=None,
        help="Optional folder to load at startup.",
    )

    metadata_parser = subparsers.add_parser("metadata", help="Inspect a single photo file and print metadata.")
    metadata_parser.add_argument("path", type=Path, help="Photo file path.")
    metadata_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )

    preview_parser = subparsers.add_parser("render-preview", help="Render a preview image for a photo file.")
    preview_parser.add_argument("path", type=Path, help="Photo file path.")
    preview_parser.add_argument("--output", type=Path, required=True, help="Output PNG path.")
    preview_parser.add_argument(
        "--metadata-source",
        type=Path,
        default=None,
        help="Optional file path to use for metadata and AF overlay while rendering another preview source.",
    )
    preview_parser.add_argument("--max-width", type=int, default=1800, help="Maximum preview width.")
    preview_parser.add_argument("--max-height", type=int, default=1400, help="Maximum preview height.")
    preview_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )

    results_parser = subparsers.add_parser("results", help="Load saved analysis results from SQLite.")
    results_parser.add_argument("folder", type=Path, help="Folder to read results for.")
    results_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Optional SQLite database path. Defaults to <folder>/.firfoto/analysis.sqlite3.",
    )
    results_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )

    feedback_get_parser = subparsers.add_parser("feedback-get", help="Load saved user overrides from SQLite.")
    feedback_get_parser.add_argument("folder", type=Path, help="Folder to read feedback for.")
    feedback_get_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Optional SQLite database path. Defaults to <folder>/.firfoto/analysis.sqlite3.",
    )
    feedback_get_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )

    feedback_set_parser = subparsers.add_parser("feedback-set", help="Persist a user override for a single photo.")
    feedback_set_parser.add_argument("folder", type=Path, help="Folder that owns the SQLite database.")
    feedback_set_parser.add_argument("path", type=Path, help="Photo path to update.")
    feedback_set_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Optional SQLite database path. Defaults to <folder>/.firfoto/analysis.sqlite3.",
    )
    feedback_set_parser.add_argument("--decision", type=str, default=None, help="Decision override.")
    feedback_set_parser.add_argument("--category", type=str, default=None, help="Category override.")
    feedback_set_parser.add_argument(
        "--tag",
        dest="tags",
        action="append",
        default=None,
        help="Tag value to persist. Repeat for multiple tags.",
    )
    feedback_set_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )

    tags_get_parser = subparsers.add_parser("tags-get", help="Load the persistent tag catalog.")
    tags_get_parser.add_argument("folder", type=Path, help="Folder that owns the SQLite database.")
    tags_get_parser.add_argument("--db", type=Path, default=None, help="Optional SQLite database path.")
    tags_get_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")

    tags_add_parser = subparsers.add_parser("tags-add", help="Add one or more tags to the persistent catalog.")
    tags_add_parser.add_argument("folder", type=Path, help="Folder that owns the SQLite database.")
    tags_add_parser.add_argument("--db", type=Path, default=None, help="Optional SQLite database path.")
    tags_add_parser.add_argument("--tag", dest="tags", action="append", default=None, help="Tag to add.")
    tags_add_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")

    tags_rename_parser = subparsers.add_parser("tags-rename", help="Rename a tag across catalog and all photos.")
    tags_rename_parser.add_argument("folder", type=Path, help="Folder that owns the SQLite database.")
    tags_rename_parser.add_argument("old_tag", type=str, help="Existing tag name.")
    tags_rename_parser.add_argument("new_tag", type=str, help="New tag name.")
    tags_rename_parser.add_argument("--db", type=Path, default=None, help="Optional SQLite database path.")
    tags_rename_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")

    tags_delete_parser = subparsers.add_parser("tags-delete", help="Delete a tag across catalog and all photos.")
    tags_delete_parser.add_argument("folder", type=Path, help="Folder that owns the SQLite database.")
    tags_delete_parser.add_argument("tag", type=str, help="Tag name to delete.")
    tags_delete_parser.add_argument("--db", type=Path, default=None, help="Optional SQLite database path.")
    tags_delete_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")

    analyze_stream_parser = subparsers.add_parser(
        "analyze-stream",
        help="Analyze a folder and stream JSON progress events.",
    )
    analyze_stream_parser.add_argument("folder", type=Path, help="Folder to analyze.")
    analyze_stream_parser.add_argument(
        "--recursive",
        action="store_true",
        help="Include subfolders.",
    )
    analyze_stream_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite database path. Defaults to <folder>/.firfoto/analysis.sqlite3.",
    )
    analyze_stream_parser.add_argument(
        "--category",
        type=str,
        default="auto",
        help="Initial subject/category hint.",
    )
    analyze_stream_parser.add_argument("--subject-label", type=str, default=None, help="Optional subject label override.")
    analyze_stream_parser.add_argument("--focus-zone", type=str, default=None, help="Optional focus zone hint.")
    analyze_stream_parser.add_argument("--camera-maker", type=str, default=None, help="Camera maker override.")
    analyze_stream_parser.add_argument("--camera-model", type=str, default=None, help="Camera model override.")
    analyze_stream_parser.add_argument("--lens-maker", type=str, default=None, help="Lens maker override.")
    analyze_stream_parser.add_argument("--lens-model", type=str, default=None, help="Lens model override.")
    analyze_stream_parser.add_argument(
        "--no-hash",
        action="store_true",
        help="Skip sha256 hashing for faster workflows.",
    )

    return parser


def _load_app_config(config_path: Path | None) -> AppConfig:
    return load_config(config_path)


def _cmd_scan(args: argparse.Namespace, config: AppConfig) -> int:
    from firfoto.core.scanner import scan_photos

    result = scan_photos(args.folder, recursive=args.recursive, config=config)
    payload = {
        "folder": str(result.folder),
        "recursive": result.recursive,
        "matched_files": [str(item.path) for item in result.files],
        "matched_count": len(result.files),
        "supported_extensions": config.scan.supported_extensions,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Folder: {result.folder}")
        print(f"Recursive: {result.recursive}")
        print(f"Matched files: {len(result.files)}")
        for item in result.files:
            print(f" - {item.path}")
    return 0


def _cmd_analyze(args: argparse.Namespace, config: AppConfig) -> int:
    options = BatchOptions(
        recursive=args.recursive,
        include_hash=not args.no_hash,
        db_path=args.db,
        category=args.category,
        subject_label=args.subject_label,
        focus_zone=args.focus_zone,
        camera_maker=args.camera_maker,
        camera_model=args.camera_model,
        lens_maker=args.lens_maker,
        lens_model=args.lens_model,
        dry_run=args.dry_run,
    )
    result = run_batch(args.folder, options=options, config=config)
    payload = {
        "folder": str(result.folder),
        "recursive": result.recursive,
        "analyzed_count": result.analyzed_count,
        "results": [item.to_dict() for item in result.results],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Folder: {result.folder}")
        print(f"Recursive: {result.recursive}")
        print(f"Analyzed files: {result.analyzed_count}")
        for item in result.results:
            print(f" - {item.identity.path} -> {item.decision.value}")
    return 0


def _cmd_show_config(args: argparse.Namespace, config: AppConfig) -> int:
    payload = config.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Default profile: {config.analysis.default_profile}")
        print(f"Supported extensions: {', '.join(config.scan.supported_extensions)}")
        print(f"Known categories: {', '.join(config.analysis.category_names())}")
    return 0


def _cmd_metadata(args: argparse.Namespace, _config: AppConfig) -> int:
    from firfoto.core.metadata import collect_basic_metadata

    metadata = collect_basic_metadata(args.path)
    payload = {
        "path": str(metadata.path),
        "size_bytes": metadata.size_bytes,
        "suffix": metadata.suffix,
        "width": metadata.width,
        "height": metadata.height,
        "camera": {
            "maker": metadata.camera.maker,
            "model": metadata.camera.model,
            "serial_number": metadata.camera.serial_number,
        },
        "lens": {
            "maker": metadata.lens.maker,
            "model": metadata.lens.model,
            "focal_length_mm": metadata.lens.focal_length_mm,
            "aperture_f": metadata.lens.aperture_f,
        },
        "capture": {
            "focal_length_mm": metadata.focal_length_mm,
            "aperture_f": metadata.aperture_f,
            "exposure_time_s": metadata.exposure_time_s,
            "iso": metadata.iso,
        },
        "af": {
            "point_index": metadata.af_point_index,
            "point_label": metadata.af_point_label,
            "info_version": metadata.af_info_version,
            "detection_method": metadata.af_detection_method,
            "area_mode": metadata.af_area_mode,
            "area_x": metadata.af_area_x,
            "area_y": metadata.af_area_y,
            "area_width": metadata.af_area_width,
            "area_height": metadata.af_area_height,
        },
        "category_hint": metadata.category_hint.value,
        "notes": metadata.notes,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Path: {metadata.path}")
        print(f"Camera: {metadata.camera.maker or '-'} {metadata.camera.model or ''}".strip())
        print(f"Lens: {metadata.lens.model or '-'}")
        print(f"AF point: {metadata.af_point_label or '-'}")
    return 0


def _cmd_render_preview(args: argparse.Namespace, _config: AppConfig) -> int:
    from firfoto.core.metadata import collect_basic_metadata
    from firfoto.gui.image_loader import (
        export_preview_image,
        focus_rect_from_subject_area,
        focus_rects_from_nikon_label,
        load_preview_frame,
    )
    from PIL import Image, ImageStat
    import math

    metadata_source = args.metadata_source or args.path

    output_path = export_preview_image(
        args.path,
        args.output,
        max_size=(args.max_width, args.max_height),
    )
    frame = load_preview_frame(args.path, max_size=(args.max_width, args.max_height))
    metadata = collect_basic_metadata(metadata_source)
    image_width = frame.image.width() if frame.image is not None else None
    image_height = frame.image.height() if frame.image is not None else None
    mean_luma = None
    suggested_exposure_ev = None
    try:
        with Image.open(output_path) as preview_image:
            grayscale = preview_image.convert("L")
            mean_luma = float(ImageStat.Stat(grayscale).mean[0])
            if mean_luma > 0:
                suggested_exposure_ev = max(-2.0, min(2.0, math.log2(128.0 / mean_luma)))
    except Exception:
        mean_luma = None
        suggested_exposure_ev = None
    camera_af_rects = []
    if image_width and image_height and metadata.af_point_label:
        camera_af_rects = [
            {
                "x": rect.x,
                "y": rect.y,
                "width": rect.width,
                "height": rect.height,
                "label": rect.label,
                "source": rect.source,
            }
            for rect in focus_rects_from_nikon_label(
                metadata.af_point_label,
                (image_width, image_height),
                camera_model=metadata.camera.model,
                area_mode=metadata.af_area_mode,
            )
        ]
    if not camera_af_rects and image_width and image_height:
        camera_af_rects = [
            {
                "x": rect.x,
                "y": rect.y,
                "width": rect.width,
                "height": rect.height,
                "label": rect.label,
                "source": rect.source,
            }
            for rect in focus_rect_from_subject_area(
                metadata_width=metadata.width,
                metadata_height=metadata.height,
                preview_width=image_width,
                preview_height=image_height,
                area_x=metadata.af_area_x,
                area_y=metadata.af_area_y,
                area_width=metadata.af_area_width,
                area_height=metadata.af_area_height,
                label=metadata.af_point_label,
            )
        ]
    payload = {
        "source_path": str(args.path),
        "metadata_source_path": str(metadata_source),
        "output_path": str(output_path),
        "max_width": args.max_width,
        "max_height": args.max_height,
        "preview_width": image_width,
        "preview_height": image_height,
        "mean_luma": mean_luma,
        "suggested_exposure_ev": suggested_exposure_ev,
        "sharp_focus_point": (
            {
                "x": frame.focus_point.x,
                "y": frame.focus_point.y,
                "radius": frame.focus_point.radius,
                "score": frame.focus_point.score,
                "label": frame.focus_point.label,
                "source": frame.focus_point.source,
            }
            if frame.focus_point is not None
            else None
        ),
        "camera_af_rects": camera_af_rects,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(output_path)
    return 0


def _default_analysis_db(folder: Path) -> Path:
    return folder / ".firfoto" / "analysis.sqlite3"


def _cmd_results(args: argparse.Namespace, _config: AppConfig) -> int:
    from firfoto.storage.sqlite import load_latest_analysis_results

    db_path = args.db or _default_analysis_db(args.folder)
    results = load_latest_analysis_results(db_path, folder=args.folder)
    payload = {
        "folder": str(args.folder),
        "db_path": str(db_path),
        "loaded_count": len(results),
        "results": [item.to_dict() for item in results],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Folder: {args.folder}")
        print(f"DB: {db_path}")
        print(f"Loaded results: {len(results)}")
    return 0


def _cmd_feedback_get(args: argparse.Namespace, _config: AppConfig) -> int:
    from firfoto.storage.sqlite import load_photo_feedback

    db_path = args.db or _default_analysis_db(args.folder)
    items = load_photo_feedback(db_path, folder=args.folder)
    payload = {
        "folder": str(args.folder),
        "db_path": str(db_path),
        "loaded_count": len(items),
        "items": items,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Folder: {args.folder}")
        print(f"DB: {db_path}")
        print(f"Loaded feedback items: {len(items)}")
    return 0


def _cmd_feedback_set(args: argparse.Namespace, _config: AppConfig) -> int:
    from firfoto.storage.sqlite import save_photo_feedback

    db_path = args.db or _default_analysis_db(args.folder)
    item = save_photo_feedback(
        db_path,
        path=args.path,
        decision_override=args.decision,
        category_override=args.category,
        tags=args.tags,
    )
    payload = {
        "folder": str(args.folder),
        "db_path": str(db_path),
        "item": item,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Saved feedback for: {args.path}")
    return 0


def _cmd_tags_get(args: argparse.Namespace, _config: AppConfig) -> int:
    from firfoto.storage.sqlite import load_tag_catalog

    db_path = args.db or _default_analysis_db(args.folder)
    tags = load_tag_catalog(db_path)
    payload = {"folder": str(args.folder), "db_path": str(db_path), "tags": tags}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("\n".join(tags))
    return 0


def _cmd_tags_add(args: argparse.Namespace, _config: AppConfig) -> int:
    from firfoto.storage.sqlite import add_tags_to_catalog

    db_path = args.db or _default_analysis_db(args.folder)
    tags = add_tags_to_catalog(db_path, args.tags or [])
    payload = {"folder": str(args.folder), "db_path": str(db_path), "tags": tags}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("\n".join(tags))
    return 0


def _cmd_tags_rename(args: argparse.Namespace, _config: AppConfig) -> int:
    from firfoto.storage.sqlite import rename_tag_globally

    db_path = args.db or _default_analysis_db(args.folder)
    tags = rename_tag_globally(db_path, args.old_tag, args.new_tag)
    payload = {"folder": str(args.folder), "db_path": str(db_path), "tags": tags}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("\n".join(tags))
    return 0


def _cmd_tags_delete(args: argparse.Namespace, _config: AppConfig) -> int:
    from firfoto.storage.sqlite import delete_tag_globally

    db_path = args.db or _default_analysis_db(args.folder)
    tags = delete_tag_globally(db_path, args.tag)
    payload = {"folder": str(args.folder), "db_path": str(db_path), "tags": tags}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("\n".join(tags))
    return 0


def _cmd_analyze_stream(args: argparse.Namespace, config: AppConfig) -> int:
    db_path = args.db or _default_analysis_db(args.folder)
    options = BatchOptions(
        recursive=args.recursive,
        include_hash=not args.no_hash,
        db_path=db_path,
        category=args.category,
        subject_label=args.subject_label,
        focus_zone=args.focus_zone,
        camera_maker=args.camera_maker,
        camera_model=args.camera_model,
        lens_maker=args.lens_maker,
        lens_model=args.lens_model,
        dry_run=False,
    )

    def emit(event: dict[str, object]) -> None:
        sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    emit({"event": "started", "folder": str(args.folder), "db_path": str(db_path)})

    def on_progress(index: int, total: int, path: Path) -> None:
        emit(
            {
                "event": "progress",
                "index": index,
                "total": total,
                "path": str(path),
            }
        )

    try:
        result = run_batch(
            args.folder,
            options=options,
            config=config,
            progress_callback=on_progress,
        )
    except KeyboardInterrupt:
        emit({"event": "cancelled", "reason": "keyboard_interrupt"})
        return 130
    except Exception as error:  # pragma: no cover - surfaced to UI
        emit({"event": "error", "message": str(error)})
        return 1

    emit(
        {
            "event": "completed",
            "analyzed_count": result.analyzed_count,
            "canceled": result.canceled,
            "db_path": str(db_path),
        }
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = _load_app_config(args.config)

    if args.command == "scan":
        return _cmd_scan(args, config)
    if args.command == "analyze":
        return _cmd_analyze(args, config)
    if args.command == "show-config":
        return _cmd_show_config(args, config)
    if args.command == "metadata":
        return _cmd_metadata(args, config)
    if args.command == "render-preview":
        return _cmd_render_preview(args, config)
    if args.command == "results":
        return _cmd_results(args, config)
    if args.command == "feedback-get":
        return _cmd_feedback_get(args, config)
    if args.command == "feedback-set":
        return _cmd_feedback_set(args, config)
    if args.command == "tags-get":
        return _cmd_tags_get(args, config)
    if args.command == "tags-add":
        return _cmd_tags_add(args, config)
    if args.command == "tags-rename":
        return _cmd_tags_rename(args, config)
    if args.command == "tags-delete":
        return _cmd_tags_delete(args, config)
    if args.command == "analyze-stream":
        return _cmd_analyze_stream(args, config)
    if args.command == "gui":
        from firfoto.gui import launch_gui

        try:
            return launch_gui(config_path=args.config, initial_folder=args.folder)
        except RuntimeError as exc:
            print(str(exc))
            return 1

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
