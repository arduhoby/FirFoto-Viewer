"""Configuration loading and defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib

from firfoto.core.models import PhotoCategory


@dataclass(slots=True)
class ScanConfig:
    supported_extensions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AnalysisConfig:
    default_profile: str = "balanced"
    categories: dict[str, dict[str, float]] = field(default_factory=dict)

    def category_names(self) -> list[str]:
        return sorted(self.categories.keys())


@dataclass(slots=True)
class AppConfig:
    scan: ScanConfig
    analysis: AnalysisConfig

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan": {"supported_extensions": list(self.scan.supported_extensions)},
            "analysis": {
                "default_profile": self.analysis.default_profile,
                "categories": dict(self.analysis.categories),
            },
        }


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "defaults.toml"


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or _default_config_path()
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    scan = ScanConfig(
        supported_extensions=[ext.lower() for ext in data["scan"]["supported_extensions"]],
    )
    analysis = AnalysisConfig(
        default_profile=data["analysis"]["default_profile"],
        categories=data["analysis"]["categories"],
    )
    return AppConfig(scan=scan, analysis=analysis)


def normalize_category_name(name: str) -> PhotoCategory:
    normalized = name.strip().lower()
    try:
        return PhotoCategory(normalized)
    except ValueError:
        return PhotoCategory.GENERAL

