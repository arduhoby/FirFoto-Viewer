"""Deterministic analysis."""

from __future__ import annotations

from pathlib import Path

from firfoto.core.image_metrics import analyze_image_file
from firfoto.core.models import AnalysisMetrics, AnalysisReason, AnalysisResult, Decision, FileIdentity, SubjectHints
from firfoto.core.metadata import BasicMetadata


def analyze_identity(identity: FileIdentity, hints: SubjectHints, metadata: BasicMetadata | None = None) -> AnalysisResult:
    metrics = AnalysisMetrics(notes=[])
    reasons: list[AnalysisReason] = []

    if metadata is not None and metadata.width and metadata.height:
        try:
            sample = analyze_image_file(identity.path)
            metrics = AnalysisMetrics(
                sharpness=sample.sharpness,
                exposure=sample.exposure,
                contrast=sample.contrast,
                noise=sample.noise,
                motion_blur_probability=sample.motion_blur_probability,
                overall_quality=sample.overall_quality,
                notes=list(sample.notes),
            )
            if sample.sharpness < 0.35:
                reasons.append(
                    AnalysisReason(
                        code="low_sharpness",
                        message="Genel netlik düşük.",
                        severity="warn",
                    )
                )
            if sample.exposure < 0.35:
                reasons.append(
                    AnalysisReason(
                        code="bad_exposure",
                        message="Işık / pozlama zayıf görünüyor.",
                        severity="warn",
                    )
                )
            if sample.noise > 0.65:
                reasons.append(
                    AnalysisReason(
                        code="high_noise",
                        message="Noise seviyesi yüksek.",
                        severity="warn",
                    )
                )
            if sample.motion_blur_probability > 0.6:
                reasons.append(
                    AnalysisReason(
                        code="possible_motion_blur",
                        message="Motion blur ihtimali yüksek.",
                        severity="warn",
                    )
                )
        except Exception as exc:
            metrics.notes.append(f"Image analysis failed: {exc.__class__.__name__}")
            reasons.append(
                AnalysisReason(
                    code="analysis_failed",
                    message="Görüntü analizi yapılamadı.",
                    severity="warn",
                )
            )
    else:
        metrics.notes.append("Image analysis skipped because file could not be decoded as an image.")
        reasons.append(
            AnalysisReason(
                code="image_decode_unavailable",
                message="Görüntü çözümlenemedi, sadece metadata kaydı alındı.",
                severity="info",
            )
        )

    if not reasons:
        reasons.append(
            AnalysisReason(
                code="analysis_completed",
                message="Temel kalite değerlendirmesi tamamlandı.",
                severity="info",
            )
        )

    return AnalysisResult(
        identity=identity,
        hints=hints,
        metrics=metrics,
        decision=Decision.SELECTED if (metrics.overall_quality or 0.0) >= 0.65 else Decision.CANDIDATE,
        reasons=reasons,
    )
