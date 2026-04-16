"""File system scanner for photo batches."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from firfoto.core.config import AppConfig


@dataclass(slots=True)
class ScanItem:
    path: Path


@dataclass(slots=True)
class ScanResult:
    folder: Path
    recursive: bool
    files: list[ScanItem]


def scan_photos(folder: Path, *, recursive: bool, config: AppConfig) -> ScanResult:
    if not folder.exists():
        raise FileNotFoundError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a folder: {folder}")

    extensions = {ext.lower().lstrip(".") for ext in config.scan.supported_extensions}
    iterator = folder.rglob("*") if recursive else folder.iterdir()
    files: list[ScanItem] = []

    for entry in iterator:
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            continue
        suffix = entry.suffix.lower().lstrip(".")
        if suffix in extensions:
            files.append(ScanItem(path=entry))

    files.sort(key=lambda item: str(item.path).lower())
    return ScanResult(folder=folder, recursive=recursive, files=files)
