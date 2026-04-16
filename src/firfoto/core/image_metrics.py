"""Deterministic image quality metrics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev

from PIL import Image, ImageChops, ImageFilter, ImageStat


@dataclass(slots=True)
class ImageMetricSample:
    sharpness: float
    exposure: float
    contrast: float
    noise: float
    motion_blur_probability: float
    overall_quality: float
    notes: list[str]


def _load_grayscale(path: Path, max_side: int = 512) -> Image.Image:
    with Image.open(path) as image:
        image = image.convert("L")
        if max(image.size) > max_side:
            image.thumbnail((max_side, max_side))
        return image.copy()


def _laplacian_variance(image: Image.Image) -> float:
    width, height = image.size
    pixels = image.load()
    values: list[float] = []
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            center = pixels[x, y]
            laplacian = (
                pixels[x - 1, y]
                + pixels[x + 1, y]
                + pixels[x, y - 1]
                + pixels[x, y + 1]
                - 4 * center
            )
            values.append(float(laplacian))
    if len(values) < 2:
        return 0.0
    return pstdev(values) ** 2


def _normalize(value: float, upper: float) -> float:
    if upper <= 0:
        return 0.0
    return max(0.0, min(1.0, value / upper))


def _flattened_pixels(image: Image.Image):
    flattened = getattr(image, "get_flattened_data", None)
    if callable(flattened):
        return flattened()
    return image.getdata()


def _compute_exposure(image: Image.Image) -> float:
    stat = ImageStat.Stat(image)
    mean_luma = stat.mean[0]
    pixels = _flattened_pixels(image)
    clipped_low = sum(1 for pixel in pixels if pixel <= 4) / max(1, image.width * image.height)
    pixels = _flattened_pixels(image)
    clipped_high = sum(1 for pixel in pixels if pixel >= 251) / max(1, image.width * image.height)
    target_distance = abs(mean_luma - 128.0) / 128.0
    exposure_score = 1.0 - min(1.0, (target_distance * 0.75) + ((clipped_low + clipped_high) * 0.5))
    return max(0.0, min(1.0, exposure_score))


def _compute_contrast(image: Image.Image) -> float:
    stat = ImageStat.Stat(image)
    spread = stat.stddev[0]
    return _normalize(spread, 64.0)


def _compute_noise(image: Image.Image) -> float:
    softened = image.filter(ImageFilter.GaussianBlur(radius=1.2))
    residual = ImageChops.difference(image, softened)
    stat = ImageStat.Stat(residual)
    return _normalize(stat.mean[0], 32.0)


def analyze_image_file(path: Path) -> ImageMetricSample:
    image = _load_grayscale(path)
    sharpness_raw = _laplacian_variance(image)
    sharpness = _normalize(sharpness_raw, 2500.0)
    exposure = _compute_exposure(image)
    contrast = _compute_contrast(image)
    noise = _compute_noise(image)
    motion_blur_probability = max(0.0, min(1.0, 1.0 - ((sharpness * 0.7) + (contrast * 0.3))))
    overall_quality = max(
        0.0,
        min(1.0, (sharpness * 0.42) + (exposure * 0.24) + (contrast * 0.18) + ((1.0 - noise) * 0.16)),
    )
    notes = [
        f"sharpness_raw={sharpness_raw:.2f}",
        f"exposure_score={exposure:.2f}",
        f"contrast_score={contrast:.2f}",
        f"noise_score={noise:.2f}",
    ]
    return ImageMetricSample(
        sharpness=sharpness,
        exposure=exposure,
        contrast=contrast,
        noise=noise,
        motion_blur_probability=motion_blur_probability,
        overall_quality=overall_quality,
        notes=notes,
    )
