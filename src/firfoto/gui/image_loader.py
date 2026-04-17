"""Preview image loading helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

try:
    import pillow_avif
except ImportError:
    pass

try:  # pragma: no cover - depends on local environment
    import rawpy
except Exception:  # pragma: no cover - raw preview falls back gracefully
    rawpy = None  # type: ignore[assignment]


RAW_SUFFIXES = {
    ".3fr",
    ".arw",
    ".cr2",
    ".cr3",
    ".dcr",
    ".dng",
    ".erf",
    ".fff",
    ".gpr",
    ".iiq",
    ".kdc",
    ".mef",
    ".mos",
    ".mrw",
    ".nef",
    ".nrw",
    ".orf",
    ".pef",
    ".ptx",
    ".raf",
    ".rw2",
    ".rwl",
    ".sr2",
    ".srf",
    ".srw",
    ".x3f",
}

SUPPORTED_IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
    ".heic",
    ".heif",
    ".avif",
    ".gif",
}

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv"}


@dataclass(slots=True)
class SharpnessBox:
    x: int
    y: int
    width: int
    height: int
    score: float


@dataclass(slots=True)
class FocusPoint:
    x: float
    y: float
    radius: float
    score: float
    label: str | None = None
    source: str = "sharpness"


@dataclass(slots=True)
class FocusRect:
    x: float
    y: float
    width: float
    height: float
    label: str | None = None
    source: str = "maker_note"


@dataclass(slots=True)
class PreviewFrame:
    image: Image.Image | None
    focus_point: FocusPoint | None = None
    error: str | None = None

    @property
    def width(self) -> int | None:
        return self.image.width if self.image else None

    @property
    def height(self) -> int | None:
        return self.image.height if self.image else None


def is_raw_file(path: Path) -> bool:
    return path.suffix.lower() in RAW_SUFFIXES




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
    mean_value = sum(values) / len(values)
    variance = sum((value - mean_value) ** 2 for value in values) / len(values)
    return variance


def _build_sharpness_boxes(image: Image.Image, *, columns: int = 12, rows: int = 8) -> list[SharpnessBox]:
    grayscale = image.convert("L")
    width, height = grayscale.size
    if width < 8 or height < 8:
        return []

    cell_width = max(1, width // columns)
    cell_height = max(1, height // rows)
    boxes: list[SharpnessBox] = []

    for row in range(rows):
        for column in range(columns):
            x0 = column * cell_width
            y0 = row * cell_height
            x1 = width if column == columns - 1 else min(width, x0 + cell_width)
            y1 = height if row == rows - 1 else min(height, y0 + cell_height)
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            crop = grayscale.crop((x0, y0, x1, y1))
            score = _laplacian_variance(crop)
            boxes.append(
                SharpnessBox(
                    x=x0,
                    y=y0,
                    width=x1 - x0,
                    height=y1 - y0,
                    score=score,
                )
            )

    if not boxes:
        return []

    max_score = max(box.score for box in boxes) or 1.0
    for box in boxes:
        box.score = max(0.0, min(1.0, box.score / max_score))
    return boxes


def _load_preview_image(path: Path, *, max_size: tuple[int, int] = (1600, 1200)) -> tuple[Image.Image | None, str | None]:
    try:
        if is_raw_file(path):
            if rawpy is None:
                return None, "RAW preview requires the rawpy package."
            with rawpy.imread(str(path)) as raw:
                rgb = raw.postprocess(
                    use_camera_wb=True,
                    no_auto_bright=True,
                    output_bps=8,
                    half_size=False,
                )
            image = Image.fromarray(rgb)
            image = ImageOps.exif_transpose(image)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            return image, None

        if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            return None, "Preview unavailable for this file type."

        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            return image.copy(), None
    except Exception as exc:  # pragma: no cover - handled by GUI
        return None, f"Preview unavailable: {exc.__class__.__name__}"


def _pick_focus_point(boxes: list[SharpnessBox]) -> FocusPoint | None:
    if not boxes:
        return None

    best_box = max(boxes, key=lambda box: box.score)
    center_x = best_box.x + (best_box.width / 2.0)
    center_y = best_box.y + (best_box.height / 2.0)
    radius = max(10.0, min(best_box.width, best_box.height) * 0.33)
    return FocusPoint(x=center_x, y=center_y, radius=radius, score=best_box.score, source="sharpness")


def _parse_nikon_focus_label(label: str | None) -> tuple[int, int, str] | None:
    if not label:
        return None

    text = label.strip().upper()
    if not text:
        return None

    letters = "ABCDEFGHI"
    for index, char in enumerate(text):
        if char.isalpha() and char in letters:
            digits = text[index + 1 :]
            if digits.isdigit():
                return letters.index(char), int(digits), text
            break
    return None


def _nikon_layout_bounds(camera_model: str | None) -> tuple[float, float, float, float]:
    model_key = (camera_model or "").strip().upper()
    x_start, x_end = 0.20, 0.80
    y_start, y_end = 0.16, 0.84
    if model_key in {"NIKON D5", "NIKON D850"}:
        x_start, x_end = 0.35, 0.65
        y_start, y_end = 0.18, 0.82
    elif model_key == "NIKON D500":
        x_start, x_end = 0.24, 0.76
        y_start, y_end = 0.16, 0.84
    return x_start, x_end, y_start, y_end


def _area_offsets(area_mode: str | None) -> list[tuple[int, int]]:
    text = (area_mode or "").strip().lower()
    if not text:
        return [(0, 0)]
    if "single" in text or "pinpoint" in text or "3d-tracking" in text or "auto" in text or "subject-tracking" in text:
        return [(0, 0)]
    if "group area (hl)" in text:
        return [(offset, 0) for offset in range(-2, 3)]
    if "group area (vl)" in text:
        return [(0, offset) for offset in range(-2, 3)]
    if "group area" in text:
        return [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)]
    if "wide (s)" in text or "dynamic area (9 points)" in text:
        return [(dx, dy) for dx in range(-1, 2) for dy in range(-1, 2)]
    if "dynamic area (21 points)" in text:
        return [
            (dx, dy)
            for dx in range(-2, 3)
            for dy in range(-2, 3)
            if not (abs(dx) == 2 and abs(dy) == 2)
        ]
    if "dynamic area (25 points)" in text:
        return [(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)]
    if "dynamic area (49 points)" in text:
        return [(dx, dy) for dx in range(-3, 4) for dy in range(-3, 4)]
    if "wide (l)" in text or "wide-area" in text or "dynamic area (51 points)" in text:
        return [(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)]
    if "dynamic area (72 points)" in text:
        return [(dx, dy) for dx in range(-3, 4) for dy in range(-3, 4)]
    return [(0, 0)]


def _merge_focus_rects(rects: list[FocusRect]) -> list[FocusRect]:
    merged = list(rects)
    changed = True
    while changed:
        changed = False
        next_rects: list[FocusRect] = []
        while merged:
            current = merged.pop(0)
            merged_this_round = False
            for index, other in enumerate(merged):
                if (
                    current.x <= other.x + other.width + 2
                    and current.x + current.width + 2 >= other.x
                    and current.y <= other.y + other.height + 2
                    and current.y + current.height + 2 >= other.y
                ):
                    left = min(current.x, other.x)
                    top = min(current.y, other.y)
                    right = max(current.x + current.width, other.x + other.width)
                    bottom = max(current.y + current.height, other.y + other.height)
                    label_parts = [part for part in [current.label, other.label] if part]
                    merged_rect = FocusRect(
                        x=left,
                        y=top,
                        width=right - left,
                        height=bottom - top,
                        label=" / ".join(dict.fromkeys(label_parts)) if label_parts else None,
                        source=current.source,
                    )
                    merged.pop(index)
                    merged.append(merged_rect)
                    changed = True
                    merged_this_round = True
                    break
            if not merged_this_round:
                next_rects.append(current)
        merged = next_rects
    return merged


def focus_rects_from_nikon_label(
    label: str | None,
    image_size: tuple[int, int],
    *,
    camera_model: str | None = None,
    area_mode: str | None = None,
) -> list[FocusRect]:
    parsed = _parse_nikon_focus_label(label)
    if parsed is None:
        return []

    width, height = image_size
    if width <= 0 or height <= 0:
        return []

    column, row, text = parsed
    total_columns = 8
    total_rows = 16
    x_start, x_end, y_start, y_end = _nikon_layout_bounds(camera_model)
    x_spacing = width * ((x_end - x_start) / max(1, total_columns))
    y_spacing = height * ((y_end - y_start) / max(1, total_rows))
    rect_width = max(10.0, x_spacing * 0.62)
    rect_height = max(10.0, y_spacing * 0.72)
    offsets = _area_offsets(area_mode)
    rects: list[FocusRect] = []

    for column_offset, row_offset in offsets:
        point_column = max(0, min(total_columns, column + column_offset))
        point_row = max(1, min(total_rows + 1, row + row_offset))
        x_ratio = point_column / total_columns
        y_ratio = (point_row - 1) / total_rows
        center_x = width * (x_start + ((x_end - x_start) * x_ratio))
        center_y = height * (y_start + ((y_end - y_start) * y_ratio))
        rects.append(
            FocusRect(
                x=center_x - (rect_width / 2.0),
                y=center_y - (rect_height / 2.0),
                width=rect_width,
                height=rect_height,
                label=text if column_offset == 0 and row_offset == 0 else None,
                source="maker_note",
            )
        )

    return _merge_focus_rects(rects)


def focus_point_from_nikon_label(
    label: str | None,
    image_size: tuple[int, int],
    camera_model: str | None = None,
) -> FocusPoint | None:
    rects = focus_rects_from_nikon_label(label, image_size, camera_model=camera_model)
    if not rects:
        return None
    first = rects[0]
    return FocusPoint(
        x=first.x + (first.width / 2.0),
        y=first.y + (first.height / 2.0),
        radius=max(first.width, first.height) / 2.0,
        score=1.0,
        label=label.strip().upper() if label else None,
        source="maker_note",
    )


def focus_rect_from_subject_area(
    *,
    metadata_width: int | None,
    metadata_height: int | None,
    preview_width: int,
    preview_height: int,
    area_x: int | None,
    area_y: int | None,
    area_width: int | None = None,
    area_height: int | None = None,
    label: str | None = None,
) -> list[FocusRect]:
    if (
        metadata_width is None
        or metadata_height is None
        or metadata_width <= 0
        or metadata_height <= 0
        or area_x is None
        or area_y is None
        or preview_width <= 0
        or preview_height <= 0
    ):
        return []

    scale_x = preview_width / metadata_width
    scale_y = preview_height / metadata_height
    rect_width = max(24.0, float(area_width or max(40, metadata_width // 12)) * scale_x)
    rect_height = max(24.0, float(area_height or max(40, metadata_height // 12)) * scale_y)
    center_x = float(area_x) * scale_x
    center_y = float(area_y) * scale_y

    return [
        FocusRect(
            x=max(0.0, center_x - (rect_width / 2.0)),
            y=max(0.0, center_y - (rect_height / 2.0)),
            width=min(rect_width, float(preview_width)),
            height=min(rect_height, float(preview_height)),
            label=label,
            source="subject_area",
        )
    ]


def load_preview_frame(path: Path, *, max_size: tuple[int, int] = (1600, 1200)) -> PreviewFrame:
    """Load a previewable image or RAW file together with sharpness boxes."""

    image, error = _load_preview_image(path, max_size=max_size)
    if image is None:
        return PreviewFrame(image=None, error=error)
    boxes = _build_sharpness_boxes(image)
    return PreviewFrame(image=image, focus_point=_pick_focus_point(boxes))


def export_preview_image(
    path: Path,
    output_path: Path,
    *,
    max_size: tuple[int, int] = (1600, 1200),
) -> Path:
    """Render a preview image and save it to disk."""

    image, error = _load_preview_image(path, max_size=max_size)
    if image is None:
        raise RuntimeError(error or "Preview unavailable.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    return output_path
