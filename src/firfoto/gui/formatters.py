"""Presentation helpers for the preview GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from firfoto.core.models import AnalysisResult


def format_quality(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def format_metric_lines(result: AnalysisResult) -> list[str]:
    metrics = result.metrics
    lines = [
        f"Netlik: {format_quality(metrics.sharpness)}",
        f"Işık / pozlama: {format_quality(metrics.exposure)}",
        f"Kontrast: {format_quality(metrics.contrast)}",
        f"Noise: {format_quality(metrics.noise)}",
        f"Motion blur riski: {format_quality(metrics.motion_blur_probability)}",
        f"Genel kalite: {format_quality(metrics.overall_quality)}",
    ]
    return lines


def _format_aperture(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"f/{value:.1f}".replace(".0", "")


def _format_shutter(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value <= 0:
        return "n/a"
    if value >= 1:
        return f"{value:.1f} s".replace(".0", "")
    denominator = round(1.0 / value)
    if denominator > 0:
        return f"1/{denominator} s"
    return f"{value:.4f} s"


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def format_identity_lines(result: AnalysisResult) -> list[str]:
    camera = result.camera
    lens = result.lens
    hints = result.hints
    lines = [
        f"Kategori: {hints.category.value}",
        f"Makine: {camera.maker or 'n/a'} {camera.model or ''}".strip(),
        f"Lens: {lens.maker or 'n/a'} {lens.model or ''}".strip(),
        f"Subject etiketi: {hints.subject_label or 'n/a'}",
        f"Odak bölgesi: {hints.focus_zone or 'n/a'}",
    ]
    return lines


def format_capture_lines(result: AnalysisResult) -> list[str]:
    width = result.extras.get("image_width")
    height = result.extras.get("image_height")
    focal_length = _number_or_none(result.extras.get("focal_length_mm") or result.lens.focal_length_mm)
    aperture = _number_or_none(result.extras.get("aperture_f") or result.lens.aperture_f)
    exposure_time = _number_or_none(result.extras.get("exposure_time_s"))
    iso = result.extras.get("iso")
    lines = [
        f"Çözünürlük: {width or 'n/a'} x {height or 'n/a'}",
        f"Odak uzaklığı: {focal_length:.0f} mm" if focal_length is not None else "Odak uzaklığı: n/a",
        f"Açıklık: {_format_aperture(aperture)}",
        f"Enstantane: {_format_shutter(exposure_time)}",
        f"ISO: {iso if iso is not None else 'n/a'}",
    ]
    return lines


def format_af_lines(result: AnalysisResult) -> list[str]:
    af_point_label = result.extras.get("af_point_label")
    af_point_index = result.extras.get("af_point_index")
    af_info_version = result.extras.get("af_info_version")
    af_detection_method = result.extras.get("af_detection_method")
    af_area_mode = result.extras.get("af_area_mode")

    lines = [
        f"AF noktası: {af_point_label or 'n/a'}",
        f"AF indeks: {af_point_index if af_point_index is not None else 'n/a'}",
        f"Algılama yöntemi: {af_detection_method or 'n/a'}",
        f"AF alan modu: {af_area_mode or 'n/a'}",
    ]
    if af_info_version:
        lines.append(f"AF Info2 sürümü: {af_info_version}")
    return lines


def format_basic_capture_lines(
    *,
    camera_maker: str | None,
    camera_model: str | None,
    lens_maker: str | None,
    lens_model: str | None,
    focal_length_mm: float | None = None,
    aperture_f: float | None = None,
    exposure_time_s: float | None = None,
    iso: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> list[str]:
    lines = [
        f"Makine: {camera_maker or 'n/a'} {camera_model or ''}".strip(),
        f"Lens: {lens_maker or 'n/a'} {lens_model or ''}".strip(),
        f"Çözünürlük: {width or 'n/a'} x {height or 'n/a'}",
        f"Odak uzaklığı: {focal_length_mm:.0f} mm" if focal_length_mm is not None else "Odak uzaklığı: n/a",
        f"Açıklık: {_format_aperture(aperture_f)}",
        f"Enstantane: {_format_shutter(exposure_time_s)}",
        f"ISO: {iso if iso is not None else 'n/a'}",
    ]
    return lines


def format_reason_lines(result: AnalysisResult) -> list[str]:
    if not result.reasons:
        return ["Kayıtlı neden yok."]
    return [f"{reason.severity.upper()}: {reason.message}" for reason in result.reasons]


def path_display_name(path: Path) -> str:
    return path.name or str(path)
