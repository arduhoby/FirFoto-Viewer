"""Config-driven rule placeholders."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RuleThresholds:
    sharpness_selected: float = 0.75
    sharpness_reject: float = 0.35
    noise_reject: float = 0.80
    motion_blur_reject: float = 0.75


@dataclass(slots=True)
class RuleSet:
    profile_name: str
    thresholds: RuleThresholds = field(default_factory=RuleThresholds)

