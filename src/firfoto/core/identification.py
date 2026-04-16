"""File identity and hashing helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from firfoto.core.models import CameraIdentity, FileIdentity, LensIdentity, SubjectHints


@dataclass(slots=True)
class IdentityBundle:
    file_identity: FileIdentity
    camera: CameraIdentity
    lens: LensIdentity
    hints: SubjectHints


def compute_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_file_identity(path: Path, *, include_hash: bool = True) -> FileIdentity:
    stat = path.stat()
    file_hash = compute_sha256(path) if include_hash else None
    return FileIdentity(path=path, size_bytes=stat.st_size, sha256=file_hash)


def build_identity_bundle(
    path: Path,
    *,
    include_hash: bool = True,
    camera: CameraIdentity | None = None,
    lens: LensIdentity | None = None,
    hints: SubjectHints | None = None,
) -> IdentityBundle:
    return IdentityBundle(
        file_identity=build_file_identity(path, include_hash=include_hash),
        camera=camera or CameraIdentity(),
        lens=lens or LensIdentity(),
        hints=hints or SubjectHints(),
    )

