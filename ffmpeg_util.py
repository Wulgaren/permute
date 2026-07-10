from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

NULL_DEVICE = "NUL" if os.name == "nt" else "/dev/null"


def check_dependencies() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(
                f"Error: {tool} not found on PATH.\n"
                "Install ffmpeg: brew install ffmpeg"
            )


_ENCODER_CACHE: set[str] | None = None
_AAC_NMR_CACHE: bool | None = None
_FPS_MODE_OPTION: str | None = None


def _aac_has_nmr() -> bool:
    """True when ffmpeg ships Lynne's native AAC encoder (aac_coder nmr)."""
    global _AAC_NMR_CACHE
    if _AAC_NMR_CACHE is None:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-h", "encoder=aac"],
            capture_output=True,
            text=True,
            check=True,
        )
        _AAC_NMR_CACHE = any(
            line.strip().startswith("nmr")
            for line in result.stdout.splitlines()
        )
    return _AAC_NMR_CACHE


def aac_encode_args(*, bitrate: str, resample_48k: bool = False) -> list[str]:
    """CBR AAC. Uses -aac_coder nmr + 48 kHz when the new encoder is available."""
    args = ["-c:a", "aac"]
    if _aac_has_nmr():
        args.extend(["-aac_coder", "nmr"])
        if resample_48k:
            args.extend(["-ar", "48000"])
    args.extend(["-b:a", bitrate])
    return args


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


def fps_sync_args(mode: str = "vfr") -> list[str]:
    """Return -fps_mode or legacy -vsync args depending on ffmpeg version."""
    global _FPS_MODE_OPTION
    if _FPS_MODE_OPTION is None:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-h", "full"],
            capture_output=True,
            text=True,
            check=True,
        )
        _FPS_MODE_OPTION = "fps_mode" if "-fps_mode" in result.stdout else "vsync"
    if _FPS_MODE_OPTION == "fps_mode":
        return ["-fps_mode", mode]
    return ["-vsync", mode]


def target_video_bitrate_k(
    duration_sec: float,
    max_size_mb: float,
    audio_bitrate_k: int = 0,
    *,
    overhead: float = 0.95,
) -> int:
    """Video bitrate (kbps) to stay under max_size_mb for the given duration."""
    if duration_sec <= 0:
        raise ValueError(f"Invalid duration: {duration_sec}")
    target_bits = max_size_mb * 1024 * 1024 * 8 * overhead
    total_bitrate_k = target_bits / duration_sec / 1000
    return max(int(total_bitrate_k - audio_bitrate_k), 64)


def h265_video_bitrate_args(
    *,
    bitrate_k: int,
    preset: str | None = "slow",
    pass_num: int | None = None,
    passlog: Path | None = None,
) -> list[str]:
    """Return ffmpeg video-encoding args for a target bitrate, preferring HEVC."""
    encoders = _available_encoders()
    if "libx265" in encoders:
        args = ["-c:v", "libx265", "-b:v", f"{bitrate_k}k"]
        if preset:
            args.extend(["-preset", preset])
        if pass_num is not None:
            args.extend(["-pass", str(pass_num)])
        if passlog is not None:
            args.extend(["-passlogfile", str(passlog)])
        args.extend(["-tag:v", "hvc1"])
        return args
    if "hevc_videotoolbox" in encoders:
        return ["-c:v", "hevc_videotoolbox", "-b:v", f"{bitrate_k}k", "-tag:v", "hvc1"]
    if "libx264" in encoders:
        args = ["-c:v", "libx264", "-b:v", f"{bitrate_k}k"]
        if preset:
            args.extend(["-preset", preset])
        if pass_num is not None:
            args.extend(["-pass", str(pass_num)])
        if passlog is not None:
            args.extend(["-passlogfile", str(passlog)])
        return args
    if "h264_videotoolbox" in encoders:
        return ["-c:v", "h264_videotoolbox", "-b:v", f"{bitrate_k}k"]
    raise RuntimeError("No H.264/H.265 video encoder found in ffmpeg")


def supports_two_pass_video() -> bool:
    encoders = _available_encoders()
    return "libx265" in encoders or "libx264" in encoders


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
        name = f"{stem}_{suffix}{ext}" if suffix else f"{stem}{ext}"
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
    return bool(probe_audio_streams(path))


@dataclass(frozen=True)
class AudioStreamInfo:
    index: int
    codec: str
    channels: int
    language: str | None
    title: str | None
    default: bool


def _channel_label(channels: int) -> str:
    if channels == 1:
        return "mono"
    if channels == 2:
        return "stereo"
    return f"{channels}ch"


def audio_stream_label(stream: AudioStreamInfo) -> str:
    parts = [stream.codec.upper(), _channel_label(stream.channels)]
    if stream.language:
        parts.append(stream.language)
    if stream.title:
        parts.append(stream.title)
    label = ", ".join(parts)
    if stream.default:
        label += " (default)"
    return label


def probe_audio_streams(path: Path) -> list[AudioStreamInfo]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries",
            "stream=index,codec_name,channels:stream_tags=language,title",
            "-show_entries", "stream_disposition=default",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout or "{}")
    streams: list[AudioStreamInfo] = []
    for entry in payload.get("streams", []):
        tags = entry.get("tags") or {}
        disposition = entry.get("disposition") or {}
        streams.append(
            AudioStreamInfo(
                index=int(entry["index"]),
                codec=entry.get("codec_name") or "unknown",
                channels=int(entry.get("channels") or 0),
                language=tags.get("language"),
                title=tags.get("title"),
                default=bool(disposition.get("default")),
            )
        )
    return streams


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

