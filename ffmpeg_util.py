from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def check_dependencies() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(
                f"Error: {tool} not found on PATH.\n"
                "Install ffmpeg: brew install ffmpeg"
            )


def run_ffmpeg(args: list[str], *, quiet: bool = False) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-y", *args]
    if not quiet:
        print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(stderr or "ffmpeg failed")


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def conversion_output(input_path: Path, *, target_ext: str, suffix_if_same: str) -> Path:
    """Use suffix only when output extension matches input extension."""
    if input_path.suffix.lower() == target_ext.lower():
        return output_path(input_path, suffix=suffix_if_same)
    return output_path(input_path, new_ext=target_ext)


def output_path(input_path: Path, suffix: str | None = None, new_ext: str | None = None) -> Path:
    """Build output path next to input. Suffix only when extension stays the same."""
    stem = input_path.stem
    ext = new_ext if new_ext is not None else input_path.suffix

    if new_ext is not None:
        name = f"{stem}{ext}"
    elif suffix:
        name = f"{stem}_{suffix}{ext}"
    else:
        name = f"{stem}{ext}"

    candidate = input_path.parent / name
    if not candidate.exists():
        return candidate

    base = candidate.stem
    for i in range(1, 1000):
        alt = input_path.parent / f"{base}_{i}{candidate.suffix}"
        if not alt.exists():
            return alt
    raise RuntimeError(f"Could not find available output name for {input_path}")


def split_output_pattern(input_path: Path) -> Path:
    """Return path pattern like movie_part%02d.mp4 for segment muxer."""
    return input_path.parent / f"{input_path.stem}_part%02d{input_path.suffix}"


def has_cover_art(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v",
            "-show_entries", "stream_disposition",
            "-of", "default=noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return "attached_pic=1" in result.stdout


def extract_cover_art(path: Path) -> Path | None:
    if not has_cover_art(path):
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    cover_path = Path(tmp.name)
    try:
        run_ffmpeg(["-i", str(path), "-map", "0:v:0", "-c", "copy", str(cover_path)], quiet=True)
    except RuntimeError:
        cover_path.unlink(missing_ok=True)
        return None
    return cover_path


def attach_cover_art(audio_path: Path, cover_path: Path) -> None:
    tmp = audio_path.with_suffix(f".tmp{audio_path.suffix}")
    run_ffmpeg([
        "-i", str(cover_path),
        "-i", str(audio_path),
        "-map", "1:a",
        "-map", "0:v",
        "-c", "copy",
        "-map_metadata", "1",
        "-disposition:v:0", "attached_pic",
        str(tmp),
    ], quiet=True)
    tmp.replace(audio_path)


def stream_copy_with_cover_args() -> list[str]:
    """ffmpeg args to stream-copy audio and keep embedded cover art."""
    return [
        "-map", "0:a",
        "-map", "0:v?",
        "-c", "copy",
        "-map_metadata", "0",
        "-disposition:v:0", "attached_pic",
    ]

