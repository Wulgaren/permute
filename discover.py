from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class MediaType(Enum):
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"
    PDF = "pdf"
    GIF = "gif"
    CUE = "cue"


AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus", ".wma", ".alac",
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv",
}
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif",
    ".tiff", ".tif", ".bmp", ".avif",
}
PDF_EXTENSIONS = {".pdf"}
GIF_EXTENSIONS = {".gif"}
CUE_EXTENSIONS = {".cue"}


@dataclass
class FileGroups:
    audio: list[Path] = field(default_factory=list)
    video: list[Path] = field(default_factory=list)
    image: list[Path] = field(default_factory=list)
    pdf: list[Path] = field(default_factory=list)
    gif: list[Path] = field(default_factory=list)
    cue: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)


def classify(path: Path) -> MediaType | None:
    ext = path.suffix.lower()
    if ext in AUDIO_EXTENSIONS:
        return MediaType.AUDIO
    if ext in VIDEO_EXTENSIONS:
        return MediaType.VIDEO
    if ext in PDF_EXTENSIONS:
        return MediaType.PDF
    if ext in IMAGE_EXTENSIONS:
        return MediaType.IMAGE
    if ext in GIF_EXTENSIONS:
        return MediaType.GIF
    if ext in CUE_EXTENSIONS:
        return MediaType.CUE
    return None


def collect_files(paths: list[Path]) -> FileGroups:
    groups = FileGroups()
    seen: set[Path] = set()

    for raw in paths:
        path = raw.expanduser().resolve()
        if not path.exists():
            print(f"Warning: path not found, skipping: {raw}")
            continue

        files: list[Path] = []
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for root, _, filenames in os.walk(path):
                for name in sorted(filenames):
                    files.append(Path(root) / name)

        for file_path in files:
            resolved = file_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)

            media_type = classify(resolved)
            if media_type is None:
                groups.skipped.append(resolved)
            elif media_type is MediaType.AUDIO:
                groups.audio.append(resolved)
            elif media_type is MediaType.VIDEO:
                groups.video.append(resolved)
            elif media_type is MediaType.IMAGE:
                groups.image.append(resolved)
            elif media_type is MediaType.PDF:
                groups.pdf.append(resolved)
            elif media_type is MediaType.GIF:
                groups.gif.append(resolved)
            elif media_type is MediaType.CUE:
                groups.cue.append(resolved)

    return groups
