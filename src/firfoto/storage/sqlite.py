"""SQLite persistence scaffolding."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from firfoto.core.models import (
    AnalysisMetrics,
    AnalysisReason,
    AnalysisResult,
    CameraIdentity,
    Decision,
    FileIdentity,
    LensIdentity,
    PhotoCategory,
    SubjectHints,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS photo_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    size_bytes INTEGER,
    sha256 TEXT,
    analyzed_at TEXT NOT NULL,
    category TEXT NOT NULL,
    camera_maker TEXT,
    camera_model TEXT,
    lens_maker TEXT,
    lens_model TEXT,
    decision TEXT NOT NULL,
    overall_quality REAL,
    metrics_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    payload_json TEXT,
    destination_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_photo_analysis_path ON photo_analysis(path);
CREATE INDEX IF NOT EXISTS idx_photo_analysis_sha256 ON photo_analysis(sha256);
CREATE INDEX IF NOT EXISTS idx_photo_analysis_category ON photo_analysis(category);
CREATE INDEX IF NOT EXISTS idx_photo_analysis_decision ON photo_analysis(decision);

CREATE TABLE IF NOT EXISTS photo_feedback (
    path TEXT PRIMARY KEY,
    decision_override TEXT,
    category_override TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_photo_feedback_decision ON photo_feedback(decision_override);
CREATE INDEX IF NOT EXISTS idx_photo_feedback_category ON photo_feedback(category_override);

CREATE TABLE IF NOT EXISTS photo_tag_catalog (
    name TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

DEFAULT_TAG_CATALOG = [
    "hero",
    "keep",
    "review",
    "af-good",
    "blur-risk",
    "low-light",
]

ADDITIONAL_COLUMNS = [
    ("size_bytes", "INTEGER"),
    ("camera_maker", "TEXT"),
    ("camera_model", "TEXT"),
    ("lens_maker", "TEXT"),
    ("lens_model", "TEXT"),
    ("overall_quality", "REAL"),
    ("payload_json", "TEXT"),
]


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA)
        existing_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(photo_analysis)").fetchall()
        }
        for column_name, column_type in ADDITIONAL_COLUMNS:
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE photo_analysis ADD COLUMN {column_name} {column_type}"
                )
        existing_tag_count = connection.execute(
            "SELECT COUNT(*) FROM photo_tag_catalog"
        ).fetchone()[0]
        if existing_tag_count == 0:
            connection.executemany(
                "INSERT OR IGNORE INTO photo_tag_catalog (name) VALUES (?)",
                [(name,) for name in DEFAULT_TAG_CATALOG],
            )
        connection.commit()


def insert_analysis_result(db_path: Path, result: AnalysisResult) -> None:
    payload = result.to_dict()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO photo_analysis (
                path, size_bytes, sha256, analyzed_at, category, camera_maker, camera_model, lens_maker, lens_model,
                decision, overall_quality, metrics_json, reasons_json, payload_json, destination_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["path"],
                payload["size_bytes"],
                payload["sha256"],
                payload["analyzed_at"],
                payload["hints"]["category"],
                payload["camera"]["maker"],
                payload["camera"]["model"],
                payload["lens"]["maker"],
                payload["lens"]["model"],
                payload["decision"],
                payload["metrics"]["overall_quality"],
                json.dumps(payload["metrics"], ensure_ascii=False),
                json.dumps(payload["reasons"], ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
                payload["destination_path"],
            ),
        )
        connection.commit()


def _result_from_payload(payload: dict[str, object]) -> AnalysisResult:
    camera_data = payload.get("camera", {}) if isinstance(payload.get("camera"), dict) else {}
    lens_data = payload.get("lens", {}) if isinstance(payload.get("lens"), dict) else {}
    hints_data = payload.get("hints", {}) if isinstance(payload.get("hints"), dict) else {}
    metrics_data = payload.get("metrics", {}) if isinstance(payload.get("metrics"), dict) else {}
    reasons_data = payload.get("reasons", []) if isinstance(payload.get("reasons"), list) else []
    extras_data = payload.get("extras", {}) if isinstance(payload.get("extras"), dict) else {}

    return AnalysisResult(
        identity=FileIdentity(
            path=Path(str(payload["path"])),
            size_bytes=int(payload.get("size_bytes") or 0),
            sha256=str(payload["sha256"]) if payload.get("sha256") else None,
        ),
        camera=CameraIdentity(
            maker=str(camera_data["maker"]) if camera_data.get("maker") else None,
            model=str(camera_data["model"]) if camera_data.get("model") else None,
            serial_number=str(camera_data["serial_number"]) if camera_data.get("serial_number") else None,
        ),
        lens=LensIdentity(
            maker=str(lens_data["maker"]) if lens_data.get("maker") else None,
            model=str(lens_data["model"]) if lens_data.get("model") else None,
            focal_length_mm=float(lens_data["focal_length_mm"]) if lens_data.get("focal_length_mm") is not None else None,
            aperture_f=float(lens_data["aperture_f"]) if lens_data.get("aperture_f") is not None else None,
        ),
        hints=SubjectHints(
            category=PhotoCategory(str(hints_data.get("category") or PhotoCategory.GENERAL.value)),
            subject_label=str(hints_data["subject_label"]) if hints_data.get("subject_label") else None,
            focus_zone=str(hints_data["focus_zone"]) if hints_data.get("focus_zone") else None,
        ),
        metrics=AnalysisMetrics(
            sharpness=float(metrics_data["sharpness"]) if metrics_data.get("sharpness") is not None else None,
            exposure=float(metrics_data["exposure"]) if metrics_data.get("exposure") is not None else None,
            contrast=float(metrics_data["contrast"]) if metrics_data.get("contrast") is not None else None,
            noise=float(metrics_data["noise"]) if metrics_data.get("noise") is not None else None,
            motion_blur_probability=float(metrics_data["motion_blur_probability"]) if metrics_data.get("motion_blur_probability") is not None else None,
            overall_quality=float(metrics_data["overall_quality"]) if metrics_data.get("overall_quality") is not None else None,
            notes=[str(note) for note in metrics_data.get("notes", [])] if isinstance(metrics_data.get("notes", []), list) else [],
        ),
        decision=Decision(str(payload.get("decision") or Decision.CANDIDATE.value)),
        reasons=[
            AnalysisReason(
                code=str(item.get("code") or "unknown"),
                message=str(item.get("message") or ""),
                severity=str(item.get("severity") or "info"),
            )
            for item in reasons_data
            if isinstance(item, dict)
        ],
        analyzed_at=datetime.fromisoformat(str(payload["analyzed_at"])),
        destination_path=Path(str(payload["destination_path"])) if payload.get("destination_path") else None,
        extras=extras_data,
    )


def _result_from_row(row: sqlite3.Row) -> AnalysisResult:
    if row["payload_json"]:
        return _result_from_payload(json.loads(row["payload_json"]))

    metrics_data = json.loads(row["metrics_json"])
    reasons_data = json.loads(row["reasons_json"])
    return AnalysisResult(
        identity=FileIdentity(
            path=Path(str(row["path"])),
            size_bytes=int(row["size_bytes"] or 0),
            sha256=row["sha256"],
        ),
        camera=CameraIdentity(
            maker=row["camera_maker"],
            model=row["camera_model"],
        ),
        lens=LensIdentity(
            maker=row["lens_maker"],
            model=row["lens_model"],
        ),
        hints=SubjectHints(category=PhotoCategory(str(row["category"]))),
        metrics=AnalysisMetrics(
            sharpness=metrics_data.get("sharpness"),
            exposure=metrics_data.get("exposure"),
            contrast=metrics_data.get("contrast"),
            noise=metrics_data.get("noise"),
            motion_blur_probability=metrics_data.get("motion_blur_probability"),
            overall_quality=metrics_data.get("overall_quality"),
            notes=[str(note) for note in metrics_data.get("notes", [])],
        ),
        decision=Decision(str(row["decision"])),
        reasons=[
            AnalysisReason(
                code=str(item.get("code") or "unknown"),
                message=str(item.get("message") or ""),
                severity=str(item.get("severity") or "info"),
            )
            for item in reasons_data
            if isinstance(item, dict)
        ],
        analyzed_at=datetime.fromisoformat(str(row["analyzed_at"])),
        destination_path=Path(str(row["destination_path"])) if row["destination_path"] else None,
    )


def load_latest_analysis_results(db_path: Path, *, folder: Path | None = None) -> list[AnalysisResult]:
    if not db_path.exists():
        return []

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT pa.*
            FROM photo_analysis pa
            INNER JOIN (
                SELECT path, MAX(id) AS latest_id
                FROM photo_analysis
                GROUP BY path
            ) latest ON latest.latest_id = pa.id
            ORDER BY LOWER(pa.path)
            """
        ).fetchall()

    results = [_result_from_row(row) for row in rows]
    if folder is None:
        return results

    resolved_folder = folder.resolve()
    filtered: list[AnalysisResult] = []
    for result in results:
        try:
            if result.identity.path.resolve().is_relative_to(resolved_folder):
                filtered.append(result)
        except FileNotFoundError:
            if resolved_folder in result.identity.path.parents:
                filtered.append(result)
    return filtered


def save_photo_feedback(
    db_path: Path,
    *,
    path: Path,
    decision_override: str | None = None,
    category_override: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, object]:
    initialize_database(db_path)
    normalized_tags = [str(tag) for tag in tags or [] if str(tag).strip()]

    with sqlite3.connect(db_path) as connection:
        if normalized_tags:
            connection.executemany(
                "INSERT OR IGNORE INTO photo_tag_catalog (name) VALUES (?)",
                [(tag,) for tag in normalized_tags],
            )
        connection.execute(
            """
            INSERT INTO photo_feedback (
                path, decision_override, category_override, tags_json, updated_at
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(path) DO UPDATE SET
                decision_override = excluded.decision_override,
                category_override = excluded.category_override,
                tags_json = excluded.tags_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(path),
                decision_override,
                category_override,
                json.dumps(normalized_tags, ensure_ascii=False),
            ),
        )
        connection.commit()

    return {
        "path": str(path),
        "decision_override": decision_override,
        "category_override": category_override,
        "tags": normalized_tags,
    }


def load_tag_catalog(db_path: Path) -> list[str]:
    if not db_path.exists():
        return list(DEFAULT_TAG_CATALOG)

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM photo_tag_catalog ORDER BY LOWER(name)"
        ).fetchall()
    return [str(row[0]) for row in rows]


def add_tags_to_catalog(db_path: Path, tags: list[str]) -> list[str]:
    initialize_database(db_path)
    normalized_tags = sorted({str(tag).strip() for tag in tags if str(tag).strip()}, key=str.lower)
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT OR IGNORE INTO photo_tag_catalog (name) VALUES (?)",
            [(tag,) for tag in normalized_tags],
        )
        connection.commit()
    return load_tag_catalog(db_path)


def rename_tag_globally(db_path: Path, old_tag: str, new_tag: str) -> list[str]:
    initialize_database(db_path)
    old_normalized = old_tag.strip()
    new_normalized = new_tag.strip()
    if not old_normalized or not new_normalized:
        return load_tag_catalog(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT path, tags_json FROM photo_feedback"
        ).fetchall()
        for row in rows:
            tags = json.loads(row["tags_json"] or "[]")
            updated = [new_normalized if str(tag) == old_normalized else str(tag) for tag in tags]
            updated = sorted(dict.fromkeys(updated))
            connection.execute(
                "UPDATE photo_feedback SET tags_json = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (json.dumps(updated, ensure_ascii=False), row["path"]),
            )
        connection.execute(
            "DELETE FROM photo_tag_catalog WHERE name = ?",
            (old_normalized,),
        )
        connection.execute(
            "INSERT OR IGNORE INTO photo_tag_catalog (name) VALUES (?)",
            (new_normalized,),
        )
        connection.commit()
    return load_tag_catalog(db_path)


def delete_tag_globally(db_path: Path, tag: str) -> list[str]:
    initialize_database(db_path)
    normalized = tag.strip()
    if not normalized:
        return load_tag_catalog(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT path, tags_json FROM photo_feedback"
        ).fetchall()
        for row in rows:
            tags = [str(item) for item in json.loads(row["tags_json"] or "[]")]
            updated = [item for item in tags if item != normalized]
            if updated != tags:
                connection.execute(
                    "UPDATE photo_feedback SET tags_json = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                    (json.dumps(updated, ensure_ascii=False), row["path"]),
                )
        connection.execute(
            "DELETE FROM photo_tag_catalog WHERE name = ?",
            (normalized,),
        )
        connection.commit()
    return load_tag_catalog(db_path)


def load_photo_feedback(db_path: Path, *, folder: Path | None = None) -> list[dict[str, object]]:
    if not db_path.exists():
        return []

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT path, decision_override, category_override, tags_json, updated_at
            FROM photo_feedback
            ORDER BY LOWER(path)
            """
        ).fetchall()

    items = [
        {
            "path": str(row["path"]),
            "decision_override": row["decision_override"],
            "category_override": row["category_override"],
            "tags": json.loads(row["tags_json"] or "[]"),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]

    if folder is None:
        return items

    resolved_folder = folder.resolve()
    filtered: list[dict[str, object]] = []
    for item in items:
        path = Path(str(item["path"]))
        try:
            if path.resolve().is_relative_to(resolved_folder):
                filtered.append(item)
        except FileNotFoundError:
            if resolved_folder in path.parents:
                filtered.append(item)
    return filtered
