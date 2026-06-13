from __future__ import annotations

import glob
import tempfile
from pathlib import Path

from cue import CueSheet, parse_cue
from ffmpeg_util import (
    attach_cover_art,
    conversion_output,
    extract_cover_art,
    output_path,
    run_ffmpeg,
    split_output_pattern,
    stream_copy_with_cover_args,
)


def to_m4a_vbr(path: Path) -> Path:
    out = conversion_output(path, target_ext=".m4a", suffix_if_same="vbr")
    run_ffmpeg(["-i", str(path), "-vn", "-c:a", "aac", "-q:a", "0", str(out)])
    return out


def to_mp3_vbr(path: Path) -> Path:
    out = conversion_output(path, target_ext=".mp3", suffix_if_same="vbr")
    run_ffmpeg(["-i", str(path), "-vn", "-c:a", "libmp3lame", "-q:a", "0", str(out)])
    return out


def to_mp3_128(path: Path) -> Path:
    out = conversion_output(path, target_ext=".mp3", suffix_if_same="128k")
    run_ffmpeg(["-i", str(path), "-vn", "-c:a", "libmp3lame", "-b:a", "128k", str(out)])
    return out


def to_h265_mp4(path: Path) -> Path:
    out = conversion_output(path, target_ext=".mp4", suffix_if_same="h265")
    run_ffmpeg([
        "-i", str(path),
        "-c:v", "libx265", "-crf", "22", "-preset", "slow", "-tag:v", "hvc1",
        "-c:a", "aac", "-q:a", "2",
        "-movflags", "+faststart",
        str(out),
    ])
    return out


def extract_audio(path: Path) -> Path:
    return to_m4a_vbr(path)


def gif_to_mp4(path: Path) -> Path:
    out = output_path(path, new_ext=".mp4")
    run_ffmpeg([
        "-i", str(path),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx265", "-crf", "28", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(out),
    ])
    return out


def optimize_gif(path: Path) -> Path:
    out = output_path(path, suffix="optimized")
    run_ffmpeg([
        "-i", str(path),
        "-vf", "split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1]paletteuse=dither=bayer",
        str(out),
    ])
    return out


def trim_audio(path: Path, start: str, end: str, *, fades: bool) -> Path:
    if fades:
        out = output_path(path, suffix="fade")
        # Reverse trick: fade in + fade out without knowing segment duration.
        fade_filter = (
            "afade=t=in:st=0:d=2,"
            "areverse,afade=t=in:st=0:d=2,areverse"
        )
        run_ffmpeg([
            "-i", str(path),
            "-ss", start, "-to", end,
            "-af", fade_filter,
            "-c:a", "aac", "-q:a", "0",
            str(out),
        ])
    else:
        out = output_path(path, suffix="trim")
        run_ffmpeg([
            "-i", str(path),
            "-ss", start, "-to", end,
            *stream_copy_with_cover_args(),
            str(out),
        ])
    return out


def split_by_duration(path: Path, minutes: float) -> list[Path]:
    seconds = int(minutes * 60)
    pattern = split_output_pattern(path)
    cover = extract_cover_art(path)
    try:
        run_ffmpeg([
            "-i", str(path),
            "-f", "segment",
            "-segment_time", str(seconds),
            "-segment_start_number", "1",
            "-reset_timestamps", "1",
            "-map", "0:a",
            "-map_metadata", "0",
            "-map_chapters", "-1",
            "-c", "copy",
            str(pattern),
        ])
        parts = sorted(Path(p) for p in glob.glob(str(pattern).replace("%02d", "*")))
        if cover:
            for part in parts:
                attach_cover_art(part, cover)
        return parts
    finally:
        if cover:
            cover.unlink(missing_ok=True)


def combine_videos(paths: list[Path]) -> Path:
    out = paths[0].parent / "combined.mp4"
    if out.exists():
        out = output_path(paths[0], suffix="combined", new_ext=".mp4")

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in paths:
            escaped = str(p).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
        list_path = f.name

    try:
        run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-c:v", "libx265", "-crf", "22", "-preset", "slow", "-tag:v", "hvc1",
            "-c:a", "aac", "-q:a", "2",
            "-movflags", "+faststart",
            str(out),
        ])
    finally:
        Path(list_path).unlink(missing_ok=True)

    return out


def split_cue_track(
    sheet: CueSheet,
    track,
    *,
    same_source: bool,
    cue_dir: Path,
) -> Path:
    ext = sheet.audio_path.suffix if same_source else ".m4a"
    name = f"{track.number:02d} - {track.title}{ext}"
    out = cue_dir / name
    if out.exists():
        out = output_path(out, suffix="1")

    args = ["-ss", str(track.start_seconds), "-i", str(sheet.audio_path)]
    if track.end_seconds is not None:
        args.extend(["-to", str(track.end_seconds)])

    if same_source:
        args.extend([*stream_copy_with_cover_args(), str(out)])
    else:
        args.extend(["-vn", "-c:a", "aac", "-q:a", "0", str(out)])

    run_ffmpeg(args)
    return out


def split_cue_file(cue_path: Path, *, same_source: bool) -> list[Path]:
    sheet = parse_cue(cue_path)
    outputs: list[Path] = []
    for track in sheet.tracks:
        out = split_cue_track(sheet, track, same_source=same_source, cue_dir=cue_path.parent)
        outputs.append(out)
    return outputs
