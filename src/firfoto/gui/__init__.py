"""Preview GUI entrypoints."""

from __future__ import annotations

from pathlib import Path


def launch_gui(config_path: Path | None = None, initial_folder: Path | None = None) -> int:
    try:
        from .qt_app import launch_gui as _launch_gui
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        if exc.name in {"PySide6", "shiboken6"}:
            raise RuntimeError("Qt (PySide6) is not available in this Python environment.") from exc
        raise

    return _launch_gui(config_path=config_path, initial_folder=initial_folder)

