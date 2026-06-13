from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CueTrack:
    number: int
    title: str
    start_seconds: float
    end_seconds: float | None


@dataclass
class CueSheet:
    audio_path: Path
    tracks: list[CueTrack]


def _index_to_seconds(index: str) -> float:
    # MM:SS:FF where FF is 75 fps frames
    parts = index.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid INDEX format: {index}")
    minutes, seconds, frames = int(parts[0]), int(parts[1]), int(parts[2])
    return minutes * 60 + seconds + frames / 75.0


def _sanitize_title(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "", title).strip()
    return cleaned or "Untitled"


def parse_cue(cue_path: Path) -> CueSheet:
    text = cue_path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines()]

    audio_file: str | None = None
    tracks: list[dict] = []
    current: dict | None = None

    for line in lines:
        if not line or line.startswith("REM"):
            continue

        if line.upper().startswith("FILE "):
            match = re.match(r'FILE\s+"(.*)"\s+\w+', line, re.IGNORECASE)
            if match:
                audio_file = match.group(1)
            else:
                rest = line[5:].strip().rsplit(None, 1)
                audio_file = rest[0].strip('"') if rest else None
            continue

        if line.upper().startswith("TRACK "):
            if current:
                tracks.append(current)
            parts = line.split()
            track_num = int(parts[1])
            current = {"number": track_num, "title": f"Track {track_num:02d}", "index": None}
            continue

        if current is None:
            continue

        if line.upper().startswith("TITLE "):
            current["title"] = line[6:].strip().strip('"')
        elif line.upper().startswith("INDEX 01 "):
            current["index"] = line[9:].strip()

    if current:
        tracks.append(current)

    if not audio_file:
        raise ValueError(f"No FILE directive found in {cue_path}")

    audio_path = (cue_path.parent / audio_file).resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Referenced audio not found: {audio_path}")

    cue_tracks: list[CueTrack] = []
    indexed = [t for t in tracks if t.get("index")]
    indexed.sort(key=lambda t: t["number"])

    for i, track in enumerate(indexed):
        start = _index_to_seconds(track["index"])
        end = None
        if i + 1 < len(indexed):
            end = _index_to_seconds(indexed[i + 1]["index"])
        cue_tracks.append(
            CueTrack(
                number=track["number"],
                title=_sanitize_title(track["title"]),
                start_seconds=start,
                end_seconds=end,
            )
        )

    if not cue_tracks:
        raise ValueError(f"No tracks with INDEX found in {cue_path}")

    return CueSheet(audio_path=audio_path, tracks=cue_tracks)
