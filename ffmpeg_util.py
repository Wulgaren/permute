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


_ENCODER_CACHE: set[str] | None = None


def _available_encoders() -> set[str]:
    global _ENCODER_CACHE
    if _ENCODER_CACHE is None:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=True,
        )
        encoders: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith("V"):
                encoders.add(parts[1])
        _ENCODER_CACHE = encoders
    return _ENCODER_CACHE


def video_scale_filter(max_width: int, max_height: int) -> str:
    """Downscale to fit within max dimensions; keep aspect ratio and even pixel sizes."""
    return (
        f"scale={max_width}:{max_height}:force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    )


def h265_video_args(*, crf: str = "22", preset: str | None = "slow") -> list[str]:
    """Return ffmpeg video-encoding args, preferring HEVC with fallbacks."""
    encoders = _available_encoders()
    if "libx265" in encoders:
        args = ["-c:v", "libx265", "-crf", crf]
        if preset:
            args.extend(["-preset", preset])
        args.extend(["-tag:v", "hvc1"])
        return args
    if "hevc_videotoolbox" in encoders:
        q = str(max(1, min(100, 100 - int(float(crf)))))
        return ["-c:v", "hevc_videotoolbox", "-q:v", q, "-tag:v", "hvc1"]
    if "libx264" in encoders:
        args = ["-c:v", "libx264", "-crf", crf]
        if preset:
            args.extend(["-preset", preset])
        return args
    if "h264_videotoolbox" in encoders:
        q = str(max(1, min(100, 100 - int(float(crf)))))
        return ["-c:v", "h264_videotoolbox", "-q:v", q]
    raise RuntimeError("No H.264/H.265 video encoder found in ffmpeg")


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


def has_audio_stream(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


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


def cue_track_metadata_args(
    *,
    title: str,
    track_number: int,
    performer: str | None = None,
    album_title: str | None = None,
) -> list[str]:
    """Override per-track tags instead of copying the source album title."""
    args = [
        "-metadata", f"title={title}",
        "-metadata", f"track={track_number}",
        "-metadata", "comment=",
        "-metadata", "synopsis=",
    ]
    if performer:
        args.extend(["-metadata", f"artist={performer}"])
    if album_title:
        args.extend(["-metadata", f"album={album_title}"])
    return args

