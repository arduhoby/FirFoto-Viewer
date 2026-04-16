"""Domain models for Firfoto."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class PhotoCategory(str, Enum):
    AERIAL = "aerial"
    SKY = "sky"
    BIRD = "bird"
    WILDLIFE = "wildlife"
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    PRODUCT = "product"
    MACRO = "macro"
    GENERAL = "general"


class Decision(str, Enum):
    SELECTED = "selected"
    REJECTED = "rejected"
    CANDIDATE = "candidate"
    BEST_OF_BURST = "best_of_burst"


@dataclass(slots=True)
class FileIdentity:
    path: Path
    size_bytes: int
    sha256: str | None = None


@dataclass(slots=True)
class CameraIdentity:
    maker: str | None = None
    model: str | None = None
    serial_number: str | None = None


@dataclass(slots=True)
class LensIdentity:
    maker: str | None = None
    model: str | None = None
    focal_length_mm: float | None = None
    aperture_f: float | None = None


@dataclass(slots=True)
class SubjectHints:
    category: PhotoCategory = PhotoCategory.GENERAL
    subject_label: str | None = None
    focus_zone: str | None = None


@dataclass(slots=True)
class AnalysisMetrics:
    sharpness: float | None = None
    exposure: float | None = None
    contrast: float | None = None
    noise: float | None = None
    motion_blur_probability: float | None = None
    overall_quality: float | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AnalysisReason:
    code: str
    message: str
    severity: str = "info"


@dataclass(slots=True)
class AnalysisResult:
    identity: FileIdentity
    camera: CameraIdentity = field(default_factory=CameraIdentity)
    lens: LensIdentity = field(default_factory=LensIdentity)
    hints: SubjectHints = field(default_factory=SubjectHints)
    metrics: AnalysisMetrics = field(default_factory=AnalysisMetrics)
    decision: Decision = Decision.CANDIDATE
    reasons: list[AnalysisReason] = field(default_factory=list)
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    destination_path: Path | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.identity.path),
            "size_bytes": self.identity.size_bytes,
            "sha256": self.identity.sha256,
            "camera": {
                "maker": self.camera.maker,
                "model": self.camera.model,
                "serial_number": self.camera.serial_number,
            },
            "lens": {
                "maker": self.lens.maker,
                "model": self.lens.model,
                "focal_length_mm": self.lens.focal_length_mm,
                "aperture_f": self.lens.aperture_f,
            },
            "hints": {
                "category": self.hints.category.value,
                "subject_label": self.hints.subject_label,
                "focus_zone": self.hints.focus_zone,
            },
            "metrics": {
                "sharpness": self.metrics.sharpness,
                "exposure": self.metrics.exposure,
                "contrast": self.metrics.contrast,
                "noise": self.metrics.noise,
                "motion_blur_probability": self.metrics.motion_blur_probability,
                "overall_quality": self.metrics.overall_quality,
                "notes": list(self.metrics.notes),
            },
            "decision": self.decision.value,
            "reasons": [
                {
                    "code": reason.code,
                    "message": reason.message,
                    "severity": reason.severity,
                }
                for reason in self.reasons
            ],
            "analyzed_at": self.analyzed_at.isoformat(),
            "destination_path": str(self.destination_path) if self.destination_path else None,
            "extras": dict(self.extras),
        }

