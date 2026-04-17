"""Metadata extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import contextlib
import io
from pathlib import Path
from typing import Any

from firfoto.core.models import CameraIdentity, LensIdentity, PhotoCategory

try:  # pragma: no cover - exercised indirectly in integration tests
    import exifread
except Exception:  # pragma: no cover - dependency may be absent in some environments
    exifread = None  # type: ignore[assignment]

try:  # pragma: no cover - exercised indirectly in integration tests
    from PIL import ExifTags, Image, ImageFilter, ImageStat
except Exception:  # pragma: no cover - dependency may be absent in some environments
    ExifTags = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]
    ImageFilter = None  # type: ignore[assignment]
    ImageStat = None  # type: ignore[assignment]


@dataclass(slots=True)
class BasicMetadata:
    path: Path
    size_bytes: int
    suffix: str
    width: int | None = None
    height: int | None = None
    camera: CameraIdentity = field(default_factory=CameraIdentity)
    lens: LensIdentity = field(default_factory=LensIdentity)
    focal_length_mm: float | None = None
    aperture_f: float | None = None
    exposure_time_s: float | None = None
    iso: int | None = None
    af_point_index: int | None = None
    af_point_label: str | None = None
    af_info_version: str | None = None
    af_detection_method: str | None = None
    af_area_mode: str | None = None
    af_area_x: int | None = None
    af_area_y: int | None = None
    af_area_width: int | None = None
    af_area_height: int | None = None
    duration_s: float | None = None
    category_hint: PhotoCategory = PhotoCategory.GENERAL
    notes: list[str] = field(default_factory=list)


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_fraction(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Fraction):
        return float(value)
    text = str(value).strip()
    if not text or text in {"0", "0/0"}:
        return None
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            return float(Fraction(int(numerator), int(denominator)))
        except Exception:
            return None
    try:
        return float(text)
    except Exception:
        return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if "/" in text:
        parsed = _parse_fraction(text)
        if parsed is None:
            return None
        return int(parsed)
    try:
        return int(float(text))
    except Exception:
        return None


def _format_aperture_value(value: Any) -> float | None:
    parsed = _parse_fraction(value)
    return parsed


def _format_mm_value(value: Any) -> float | None:
    parsed = _parse_fraction(value)
    return parsed


def _map_exif_tag_name(tag_id: int) -> str | None:
    if ExifTags is None:
        return None
    return ExifTags.TAGS.get(tag_id)


def _read_pillow_metadata(path: Path) -> tuple[int | None, int | None, CameraIdentity, LensIdentity]:
    if Image is None:
        return None, None, CameraIdentity(), LensIdentity()

    with Image.open(path) as image:
        width, height = image.size
        exif = image.getexif()
        tagged: dict[str, Any] = {}
        if exif:
            for tag_id, value in exif.items():
                name = _map_exif_tag_name(tag_id)
                if name:
                    tagged[name] = value

        camera = CameraIdentity(
            maker=_normalize_text(tagged.get("Make")),
            model=_normalize_text(tagged.get("Model")),
            serial_number=_normalize_text(tagged.get("BodySerialNumber") or tagged.get("Body Serial Number")),
        )
        lens = LensIdentity(
            maker=_normalize_text(tagged.get("LensMake") or tagged.get("Lens Make")),
            model=_normalize_text(tagged.get("LensModel") or tagged.get("Lens Model")),
            focal_length_mm=_parse_fraction(tagged.get("FocalLength")),
            aperture_f=_parse_fraction(tagged.get("FNumber")),
        )
        return width, height, camera, lens


def _read_exifread_metadata(path: Path) -> tuple[CameraIdentity, LensIdentity]:
    if exifread is None:
        return CameraIdentity(), LensIdentity()
    with path.open("rb") as handle:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            tags = exifread.process_file(handle, details=False, stop_tag="UNDEF")

    def get(*names: str) -> Any:
        for name in names:
            if name in tags:
                return tags[name]
        return None

    camera = CameraIdentity(
        maker=_normalize_text(get("Image Make", "EXIF MakerNote")),
        model=_normalize_text(get("Image Model")),
        serial_number=_normalize_text(get("EXIF BodySerialNumber", "EXIF CameraSerialNumber")),
    )
    lens = LensIdentity(
        maker=_normalize_text(get("EXIF LensMake", "Image LensMake")),
        model=_normalize_text(get("EXIF LensModel", "Image LensModel")),
        focal_length_mm=_parse_fraction(get("EXIF FocalLength")),
        aperture_f=_parse_fraction(get("EXIF FNumber")),
    )
    return camera, lens


def _read_exifread_tags(path: Path) -> dict[str, Any]:
    if exifread is None:
        return {}
    with path.open("rb") as handle:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return exifread.process_file(handle, details=True, stop_tag="UNDEF")


def _tag_values(tag: Any) -> list[Any]:
    if tag is None:
        return []
    values = getattr(tag, "values", None)
    if values is not None:
        return list(values)
    try:
        return list(tag)
    except Exception:
        return []


def _extract_nikon_info(tags: dict[str, Any], camera: CameraIdentity) -> dict[str, Any]:
    """Extract Nikon specific MakerNote information."""
    af_info = tags.get("MakerNote AFInfo2")
    values = _tag_values(af_info)
    results: dict[str, Any] = {}

    if len(values) >= 69:
        results["af_info_version"] = "".join(chr(int(value)) for value in values[:4] if isinstance(value, int) and 32 <= int(value) <= 126)
        results["af_detection_method"] = {
            0: "Phase Detect", 1: "Contrast Detect", 2: "Hybrid",
        }.get(int(values[4]) if len(values) > 4 and isinstance(values[4], int) else -1)
        results["af_area_mode"] = {
            0: "Single Area", 1: "Dynamic Area", 2: "Dynamic Area (closest subject)",
            3: "Group Dynamic", 4: "Dynamic Area (9 points)", 5: "Dynamic Area (21 points)",
            6: "Dynamic Area (51 points)", 7: "Dynamic Area (51 points, 3D-tracking)",
            8: "Auto-area", 9: "Dynamic Area (3D-tracking)", 13: "Group Area",
            14: "Dynamic Area (25 points)", 15: "Dynamic Area (72 points)",
            16: "Group Area (HL)", 17: "Group Area (VL)", 18: "Dynamic Area (49 points)",
            128: "Single", 129: "Auto (41 points)", 192: "Pinpoint",
            193: "Single", 195: "Wide (S)", 196: "Wide (L)", 197: "Auto",
            201: "Wide-area AF", 204: "Dynamic Area (S)", 207: "3D-tracking",
        }.get(int(values[5]) if len(values) > 5 and isinstance(values[5], int) else -1)

        af_point_index = int(values[68]) if len(values) > 68 and isinstance(values[68], int) else None
        results["af_point_index"] = af_point_index
        if af_point_index is not None:
            if camera.model and camera.model.upper() in {"NIKON D5", "NIKON D500", "NIKON D850"}:
                results["af_point_label"] = _nikon_153_point_label(af_point_index)
            else:
                results["af_point_label"] = str(af_point_index)
    return results


def _extract_fujifilm_info(tags: dict[str, Any]) -> dict[str, Any]:
    """Extract Fujifilm specific MakerNote information."""
    results: dict[str, Any] = {}
    
    # Lens Info
    lens_model = _normalize_text(tags.get("MakerNote LensModel") or tags.get("MakerNote LensInfo"))
    if lens_model:
        results["lens_model"] = lens_model

    # Focus Info
    focus_mode = _normalize_text(tags.get("MakerNote FocusMode"))
    if focus_mode:
        results["af_detection_method"] = focus_mode
    
    af_area_mode = _normalize_text(tags.get("MakerNote AFMode"))
    if af_area_mode:
        results["af_area_mode"] = af_area_mode

    # Some Fuji models store focus point in MakerNote FocusPixel
    focus_pixel = tags.get("MakerNote FocusPixel")
    if focus_pixel:
        values = _tag_values(focus_pixel)
        if len(values) >= 2:
            results["af_area_x"] = int(values[0])
            results["af_area_y"] = int(values[1])
            results["af_point_label"] = "Active Area"

    return results


def _extract_canon_info(tags: dict[str, Any]) -> dict[str, Any]:
    """Extract Canon specific MakerNote information."""
    results: dict[str, Any] = {}
    
    # Higher quality lens name often in these tags
    lens_model = _normalize_text(tags.get("MakerNote LensModel") or tags.get("EXIF LensModel"))
    if lens_model:
        results["lens_model"] = lens_model

    focus_mode = _normalize_text(tags.get("MakerNote FocusMode"))
    if focus_mode:
        results["af_detection_method"] = focus_mode

    # Canon AF Point mapping can be very complex, adding basic support
    af_point = tags.get("MakerNote AFPointsInFocus")
    if af_point:
        results["af_point_label"] = f"AF Point {af_point}"

    return results


def _extract_subject_area(tags: dict[str, Any]) -> tuple[int | None, int | None, int | None, int | None]:
    values = _tag_values(tags.get("EXIF SubjectArea") or tags.get("Image SubjectArea"))
    parsed = [_parse_int(value) for value in values]
    numbers = [value for value in parsed if value is not None]
    if len(numbers) >= 4:
        return numbers[0], numbers[1], max(1, numbers[2]), max(1, numbers[3])
    if len(numbers) >= 3:
        diameter = max(1, numbers[2])
        return numbers[0], numbers[1], diameter, diameter
    if len(numbers) >= 2:
        return numbers[0], numbers[1], None, None

    values = _tag_values(tags.get("EXIF SubjectLocation") or tags.get("Image SubjectLocation"))
    parsed = [_parse_int(value) for value in values]
    numbers = [value for value in parsed if value is not None]
    if len(numbers) >= 2:
        return numbers[0], numbers[1], None, None
    return None, None, None, None


def _extract_brand_focus_hint(
    tags: dict[str, Any],
    camera_maker: str | None,
) -> tuple[str | None, str | None, str | None]:
    maker = (camera_maker or "").strip().lower()
    if not maker:
        return None, None, None

    if "canon" not in maker and "sony" not in maker:
        return None, None, None

    label: str | None = None
    area_mode: str | None = None
    detection_method: str | None = None

    for key, value in tags.items():
        lowered = key.lower()
        value_text = _normalize_text(value)
        if value_text is None:
            continue
        if label is None and (
            "af point" in lowered
            or "focus point" in lowered
            or "afpointsinfocus" in lowered
            or "selectedafpoint" in lowered
        ):
            label = value_text
        if area_mode is None and ("af area" in lowered or "focus area" in lowered):
            area_mode = value_text
        if detection_method is None and ("af method" in lowered or "focus mode" in lowered):
            detection_method = value_text

    if label is None:
        x, y, _, _ = _extract_subject_area(tags)
        if x is not None and y is not None:
            label = "Active area"

    return label, detection_method, area_mode


def _extract_sony_info(tags: dict[str, Any]) -> dict[str, Any]:
    """Extract Sony specific MakerNote information."""
    results: dict[str, Any] = {}
    
    detection_method = _normalize_text(tags.get("MakerNote FocusMode"))
    if detection_method == "Unknown":
        detection_method = None
    results["af_detection_method"] = detection_method

    area_mode = _normalize_text(tags.get("MakerNote AFAreaMode"))
    if area_mode == "Unknown":
        area_mode = None
    results["af_area_mode"] = area_mode

    label, fallback_dm, fallback_am = _extract_brand_focus_hint(tags, "sony")
    results["af_point_label"] = label
    if not results["af_detection_method"]: results["af_detection_method"] = fallback_dm
    if not results["af_area_mode"]: results["af_area_mode"] = fallback_am

    return results


def _extract_nikon_lens_identity(
    tags: dict[str, Any],
    existing_lens: LensIdentity,
    focal_length_mm: float | None,
    aperture_f: float | None,
) -> tuple[LensIdentity, list[str]]:
    notes: list[str] = []
    lens = LensIdentity(
        maker=existing_lens.maker,
        model=existing_lens.model,
        focal_length_mm=existing_lens.focal_length_mm,
        aperture_f=existing_lens.aperture_f,
    )

    if lens.maker and lens.model:
        return lens, notes

    lens_type = _parse_int(tags.get("MakerNote LensType"))
    lens_range_tag = tags.get("MakerNote LensMinMaxFocalMaxAperture")
    lens_range_values = _tag_values(lens_range_tag)
    range_min = _format_mm_value(lens_range_values[0]) if len(lens_range_values) > 0 else None
    range_max = _format_mm_value(lens_range_values[1]) if len(lens_range_values) > 1 else None
    max_aperture_min = _format_aperture_value(lens_range_values[2]) if len(lens_range_values) > 2 else None
    max_aperture_max = _format_aperture_value(lens_range_values[3]) if len(lens_range_values) > 3 else None

    if lens.maker is None:
        if lens_type is not None:
            lens.maker = "Nikon"

    if lens.model is None:
        if range_min is not None and range_max is not None:
            if max_aperture_min is not None and max_aperture_max is not None:
                if abs(max_aperture_min - max_aperture_max) < 0.01:
                    aperture_text = f"f/{max_aperture_min:.1f}".replace(".0", "")
                else:
                    aperture_text = f"f/{max_aperture_min:.1f}-{max_aperture_max:.1f}".replace(".0", "")
                lens.model = f"{int(round(range_min))}-{int(round(range_max))}mm {aperture_text}"
            else:
                lens.model = f"{int(round(range_min))}-{int(round(range_max))}mm"
            notes.append("Lens model inferred from Nikon MakerNote range.")
        elif focal_length_mm is not None or aperture_f is not None:
            focal_text = f"{int(round(focal_length_mm))}mm" if focal_length_mm is not None else "lens"
            if aperture_f is not None:
                lens.model = f"{focal_text} f/{aperture_f:.1f}".replace(".0", "")
            else:
                lens.model = focal_text
            notes.append("Lens model inferred from focal length and aperture.")

    if lens.maker is not None and lens.model is None and lens_type is not None:
        lens.model = f"LensType {lens_type}"
        notes.append("Lens type available but exact model is unknown.")

    if lens.focal_length_mm is None:
        lens.focal_length_mm = focal_length_mm
    if lens.aperture_f is None:
        lens.aperture_f = aperture_f

    return lens, notes


def _extract_video_info(path: Path) -> dict[str, Any]:
    """Use ffprobe to extract video resolution and duration."""
    import subprocess
    import json
    
    results: dict[str, Any] = {}
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        data = json.loads(output)
        
        # Get duration
        format_data = data.get("format", {})
        results["duration_s"] = _parse_fraction(format_data.get("duration"))
        
        # Get video stream info
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                results["width"] = _parse_int(stream.get("width"))
                results["height"] = _parse_int(stream.get("height"))
                break
    except Exception:
        pass  # Fallback to defaults
    return results


def _extract_generic_info(tags: dict[str, Any]) -> dict[str, Any]:
    """Generic fallback for MakerNote extraction."""
    results: dict[str, Any] = {}
    label, dm, am = _extract_brand_focus_hint(tags, None)
    results["af_point_label"] = label
    results["af_detection_method"] = dm
    results["af_area_mode"] = am
    return results


def infer_category_from_path(path: Path) -> PhotoCategory:
    tokens = " ".join(path.parts).lower()
    mapping = {
        PhotoCategory.BIRD: ("bird", "avian", "wildlife"),
        PhotoCategory.WILDLIFE: ("wildlife", "animal", "nature"),
        PhotoCategory.PORTRAIT: ("portrait", "people", "face"),
        PhotoCategory.LANDSCAPE: ("landscape", "mountain", "forest", "sea", "sunset"),
        PhotoCategory.SKY: ("sky", "cloud", "clouds", "sunrise", "sunset"),
        PhotoCategory.AERIAL: ("aerial", "drone", "air", "flight"),
        PhotoCategory.PRODUCT: ("product", "catalog", "studio"),
        PhotoCategory.MACRO: ("macro", "closeup", "close-up"),
    }
    for category, keywords in mapping.items():
        if any(keyword in tokens for keyword in keywords):
            return category
    return PhotoCategory.GENERAL


def collect_basic_metadata(path: Path) -> BasicMetadata:
    stat = path.stat()
    width: int | None = None
    height: int | None = None
    camera = CameraIdentity()
    lens = LensIdentity()
    focal_length_mm: float | None = None
    aperture_f: float | None = None
    exposure_time_s: float | None = None
    iso: int | None = None
    af_point_index: int | None = None
    af_point_label: str | None = None
    af_info_version: str | None = None
    af_detection_method: str | None = None
    af_area_mode: str | None = None
    af_area_x: int | None = None
    af_area_y: int | None = None
    af_area_width: int | None = None
    af_area_height: int | None = None
    duration_s: float | None = None
    notes: list[str] = []

    suffix_lower = path.suffix.lower()
    from firfoto.gui.image_loader import VIDEO_SUFFIXES
    if suffix_lower in VIDEO_SUFFIXES:
        video_info = _extract_video_info(path)
        return BasicMetadata(
            path=path,
            size_bytes=stat.st_size,
            suffix=suffix_lower,
            width=video_info.get("width"),
            height=video_info.get("height"),
            duration_s=video_info.get("duration_s"),
            category_hint=PhotoCategory.GENERAL,
            notes=["Video file metadata extracted via ffprobe."],
        )

    try:
        width, height, camera, lens = _read_pillow_metadata(path)
        focal_length_mm = lens.focal_length_mm
        aperture_f = lens.aperture_f
    except Exception as exc:
        notes.append(f"Pillow metadata unavailable: {exc.__class__.__name__}")

    try:
        tags = _read_exifread_tags(path)
        exif_camera, exif_lens = _read_exifread_metadata(path)
        camera = CameraIdentity(
            maker=camera.maker or exif_camera.maker,
            model=camera.model or exif_camera.model,
            serial_number=camera.serial_number or exif_camera.serial_number,
        )
        lens = LensIdentity(
            maker=lens.maker or exif_lens.maker,
            model=lens.model or exif_lens.model,
            focal_length_mm=lens.focal_length_mm or exif_lens.focal_length_mm,
            aperture_f=lens.aperture_f or exif_lens.aperture_f,
        )
        focal_length_mm = focal_length_mm or exif_lens.focal_length_mm
        aperture_f = aperture_f or exif_lens.aperture_f
        lens, lens_notes = _extract_nikon_lens_identity(tags, lens, focal_length_mm, aperture_f)
        if lens_notes:
            notes.extend(lens_notes)
        if tags:
            exposure_time_s = _parse_fraction(
                tags.get("EXIF ExposureTime")
                or tags.get("Image ExposureTime")
                or tags.get("EXIF ShutterSpeedValue")
            )
            iso = _parse_int(
                tags.get("EXIF ISOSpeedRatings")
                or tags.get("EXIF PhotographicSensitivity")
                or tags.get("Image ISOSpeedRatings")
            )
        # Brand-Specific Fine-tuning
        maker_lower = (camera.maker or "").lower()
        brand_data: dict[str, Any] = {}
        if "nikon" in maker_lower:
            brand_data = _extract_nikon_info(tags, camera)
        elif "fuji" in maker_lower:
            brand_data = _extract_fujifilm_info(tags)
        elif "canon" in maker_lower:
            brand_data = _extract_canon_info(tags)
        elif "sony" in maker_lower:
            brand_data = _extract_sony_info(tags)
        else:
            brand_data = _extract_generic_info(tags)

        # Merge Brand Data
        if brand_data.get("lens_model"):
            lens.model = brand_data["lens_model"]
        af_point_index = brand_data.get("af_point_index", af_point_index)
        af_point_label = brand_data.get("af_point_label", af_point_label)
        af_info_version = brand_data.get("af_info_version", af_info_version)
        af_detection_method = brand_data.get("af_detection_method", af_detection_method)
        af_area_mode = brand_data.get("af_area_mode", af_area_mode)
        af_area_x = brand_data.get("af_area_x", af_area_x)
        af_area_y = brand_data.get("af_area_y", af_area_y)

        af_area_x_sub, af_area_y_sub, af_area_w_sub, af_area_h_sub = _extract_subject_area(tags)
        af_area_x = af_area_x or af_area_x_sub
        af_area_y = af_area_y or af_area_y_sub
        af_area_width = af_area_w_sub
        af_area_height = af_area_h_sub

        if af_point_label is None:
            af_point_label, fb_dm, fb_am = _extract_brand_focus_hint(tags, camera.maker)
            af_detection_method = af_detection_method or fb_dm
            af_area_mode = af_area_mode or fb_am

        if af_point_label:
            notes.append(f"AF point: {af_point_label}")
        elif af_area_x is not None and af_area_y is not None:
            notes.append("AF area coordinates available.")
    except Exception as exc:
        notes.append(f"EXIF metadata unavailable: {exc.__class__.__name__}")

    return BasicMetadata(
        path=path,
        size_bytes=stat.st_size,
        suffix=path.suffix.lower(),
        width=width,
        height=height,
        camera=camera,
        lens=lens,
        focal_length_mm=focal_length_mm,
        aperture_f=aperture_f,
        exposure_time_s=exposure_time_s,
        iso=iso,
        af_point_index=af_point_index,
        af_point_label=af_point_label,
        af_info_version=af_info_version,
        af_detection_method=af_detection_method,
        af_area_mode=af_area_mode,
        af_area_x=af_area_x,
        af_area_y=af_area_y,
        af_area_width=af_area_width,
        af_area_height=af_area_height,
        category_hint=infer_category_from_path(path),
        notes=notes,
    )
