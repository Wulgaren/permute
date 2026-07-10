from __future__ import annotations

import glob
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cue import CueSheet, parse_cue
from ffmpeg_util import (
    NULL_DEVICE,
    aac_encode_args,
    attach_cover_art,
    conversion_output,
    cue_track_metadata_args,
    extract_cover_art,
    fps_sync_args,
    h265_video_args,
    h265_video_bitrate_args,
    has_audio_stream,
    output_path,
    probe_duration,
    run_ffmpeg,
    split_output_pattern,
    stream_copy_with_cover_args,
    supports_two_pass_video,
    target_video_bitrate_k,
    video_scale_filter,
)

BEST_M4A_BITRATE = "256k"
VIDEO_AAC_BITRATE = "160k"


@dataclass(frozen=True)
class VideoCompressPreset:
    name: str
    max_width: int
    max_height: int
    crf: str
    encoder_preset: str | None
    suffix: str
    max_size_mb: float | None = None


# HandBrake-inspired presets: H.265, downscale-to-fit, AAC 160k audio.
VIDEO_COMPRESS_PRESETS: list[VideoCompressPreset] = [
    VideoCompressPreset("Max 10 MB", 1280, 720, "24", "fast", "10mb", max_size_mb=10),
    VideoCompressPreset("Fast 1080p", 1920, 1080, "24", "fast", "1080p"),
    VideoCompressPreset("Fast 720p", 1280, 720, "24", "fast", "720p"),
    VideoCompressPreset("Fast 480p", 854, 480, "26", "fast", "480p"),
]


def to_m4a(path: Path, *, audio_stream: int | None = None) -> Path:
    if audio_stream is not None and audio_stream > 0:
        out = output_path(path, suffix=f"track{audio_stream + 1}", new_ext=".m4a")
    else:
        out = conversion_output(path, target_ext=".m4a", suffix_if_same="256k")

    map_args = ["-map", f"0:a:{audio_stream}"] if audio_stream is not None else ["-vn"]
    run_ffmpeg([
        "-i", str(path),
        *map_args,
        *aac_encode_args(bitrate=BEST_M4A_BITRATE, resample_48k=True),
        str(out),
    ])
    return out


def to_mp3_vbr(path: Path) -> Path:
    out = conversion_output(path, target_ext=".mp3", suffix_if_same="vbr")
    run_ffmpeg(["-i", str(path), "-vn", "-c:a", "libmp3lame", "-q:a", "0", str(out)])
    return out


def to_mp3_128(path: Path) -> Path:
    out = conversion_output(path, target_ext=".mp3", suffix_if_same="128k")
    run_ffmpeg(["-i", str(path), "-vn", "-c:a", "libmp3lame", "-b:a", "128k", str(out)])
    return out


def _atempo_chain(speed: float) -> str:
    """Build atempo filter chain (each atempo stage must stay within 0.5–2.0)."""
    filters: list[str] = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining}")
    return ",".join(filters)


def _speed_suffix(speed: float) -> str:
    label = str(int(speed)) if speed == int(speed) else str(speed)
    return f"{label}x"


def speed_up_video(path: Path, speed: float) -> Path:
    out = conversion_output(path, target_ext=".mp4", suffix_if_same=_speed_suffix(speed))
    args = ["-i", str(path), "-vf", f"setpts=PTS/{speed}"]
    if has_audio_stream(path):
        args.extend([
            "-af", _atempo_chain(speed),
            *aac_encode_args(bitrate=VIDEO_AAC_BITRATE, resample_48k=True),
        ])
    else:
        args.append("-an")
    args.extend([
        *h265_video_args(),
        "-movflags", "+faststart",
        str(out),
    ])
    run_ffmpeg(args)
    return out


def to_h265_mp4(path: Path) -> Path:
    out = conversion_output(path, target_ext=".mp4", suffix_if_same="h265")
    run_ffmpeg([
        "-i", str(path),
        *h265_video_args(),
        *aac_encode_args(bitrate=VIDEO_AAC_BITRATE, resample_48k=True),
        "-movflags", "+faststart",
        str(out),
    ])
    return out


def _compress_video_target_size(path: Path, preset: VideoCompressPreset, out: Path) -> None:
    assert preset.max_size_mb is not None
    duration = probe_duration(path)
    has_audio = has_audio_stream(path)
    audio_k = 160 if has_audio else 0
    video_k = target_video_bitrate_k(duration, preset.max_size_mb, audio_k)
    print(f"  Target: ≤{preset.max_size_mb:g} MB ({duration:.1f}s → {video_k}k video + {audio_k}k audio)")

    scale = ["-vf", video_scale_filter(preset.max_width, preset.max_height)]
    input_args = ["-i", str(path), *scale]

    if supports_two_pass_video():
        with tempfile.TemporaryDirectory() as tmpdir:
            passlog = Path(tmpdir) / "ffmpeg2pass"
            run_ffmpeg([
                *input_args,
                *h265_video_bitrate_args(
                    bitrate_k=video_k,
                    preset=preset.encoder_preset,
                    pass_num=1,
                    passlog=passlog,
                ),
                "-an",
                "-f", "null",
                NULL_DEVICE,
            ])
            args = [*input_args]
            if has_audio:
                args.extend(aac_encode_args(bitrate=VIDEO_AAC_BITRATE, resample_48k=True))
            else:
                args.append("-an")
            args.extend([
                *h265_video_bitrate_args(
                    bitrate_k=video_k,
                    preset=preset.encoder_preset,
                    pass_num=2,
                    passlog=passlog,
                ),
                "-movflags", "+faststart",
                str(out),
            ])
            run_ffmpeg(args)
    else:
        args = [*input_args]
        if has_audio:
            args.extend(aac_encode_args(bitrate=VIDEO_AAC_BITRATE, resample_48k=True))
        else:
            args.append("-an")
        args.extend([
            *h265_video_bitrate_args(bitrate_k=video_k, preset=preset.encoder_preset),
            "-movflags", "+faststart",
            str(out),
        ])
        run_ffmpeg(args)


def compress_video(path: Path, preset: VideoCompressPreset) -> Path:
    out = conversion_output(path, target_ext=".mp4", suffix_if_same=preset.suffix)
    if preset.max_size_mb is not None:
        _compress_video_target_size(path, preset, out)
        return out

    args = [
        "-i", str(path),
        "-vf", video_scale_filter(preset.max_width, preset.max_height),
    ]
    if has_audio_stream(path):
        args.extend(aac_encode_args(bitrate=VIDEO_AAC_BITRATE, resample_48k=True))
    else:
        args.append("-an")
    args.extend([
        *h265_video_args(crf=preset.crf, preset=preset.encoder_preset),
        "-movflags", "+faststart",
        str(out),
    ])
    run_ffmpeg(args)
    return out


def extract_audio(path: Path, *, audio_stream: int | None = None) -> Path:
    return to_m4a(path, audio_stream=audio_stream)


def to_best_jpg(path: Path) -> Path:
    out = conversion_output(path, target_ext=".jpg", suffix_if_same="best")
    run_ffmpeg([
        "-i", str(path),
        "-q:v", "2",
        str(out),
    ])
    return out


def images_to_pdf(paths: list[Path]) -> Path:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Pillow required for image→PDF. Install: pip install Pillow"
        ) from exc

    if len(paths) == 1:
        out = conversion_output(paths[0], target_ext=".pdf", suffix_if_same="converted")
    else:
        out = paths[0].parent / "combined.pdf"
        if out.exists():
            out = output_path(paths[0], suffix="combined", new_ext=".pdf")

    images = []
    try:
        for path in paths:
            img = Image.open(path)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            images.append(img)
        images[0].save(out, save_all=True, append_images=images[1:])
    finally:
        for img in images:
            img.close()
    return out


def pdf_to_jpg(path: Path) -> list[Path]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF required for PDF→JPG. Install: pip install -r requirements.txt"
        ) from exc

    doc = fitz.open(path)
    outputs: list[Path] = []
    try:
        page_count = len(doc)
        for index, page in enumerate(doc):
            if page_count == 1:
                out = output_path(path, new_ext=".jpg")
            else:
                base = path.parent / f"{path.stem}_page{index + 1:03d}.jpg"
                out = base if not base.exists() else output_path(
                    path.parent / f"{path.stem}_page{index + 1:03d}",
                    new_ext=".jpg",
                )
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            pix.save(str(out), jpg_quality=95)
            outputs.append(out)
    finally:
        doc.close()
    return outputs


def combine_pdfs(paths: list[Path]) -> Path:
    try:
        from pypdf import PdfWriter
    except ImportError as exc:
        raise RuntimeError(
            "pypdf required to merge PDFs. Install: pip install -r requirements.txt"
        ) from exc

    out = paths[0].parent / "combined.pdf"
    if out.exists():
        out = output_path(paths[0], suffix="combined", new_ext=".pdf")

    writer = PdfWriter()
    for pdf_path in paths:
        writer.append(str(pdf_path))
    with open(out, "wb") as handle:
        writer.write(handle)
    return out


def video_frame_jpg(path: Path, *, frame_index: int) -> Path:
    """Extract a single frame as JPEG (frame_index is 0-based)."""
    out = output_path(path, suffix=f"frame{frame_index + 1}", new_ext=".jpg")
    run_ffmpeg([
        "-i", str(path),
        "-vf", f"select=eq(n\\,{frame_index})",
        *fps_sync_args("vfr"),
        "-frames:v", "1",
        "-q:v", "2",
        str(out),
    ])
    return out


def gif_to_mp4(path: Path) -> Path:
    out = output_path(path, new_ext=".mp4")
    run_ffmpeg([
        "-i", str(path),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        *h265_video_args(crf="28", preset=None),
        "-pix_fmt", "yuv420p",
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


def trim_audio(
    path: Path, start: str, end: str, *, fade_in: bool, fade_out: bool,
) -> Path:
    if fade_in or fade_out:
        out = conversion_output(path, target_ext=".m4a", suffix_if_same="fade")
        parts: list[str] = []
        if fade_in:
            parts.append("afade=t=in:st=0:d=2")
        if fade_out:
            # Reverse trick: fade out without knowing segment duration.
            parts.append("areverse,afade=t=in:st=0:d=2,areverse")
        fade_filter = ",".join(parts)
        cover = extract_cover_art(path)
        try:
            run_ffmpeg([
                "-i", str(path),
                "-ss", start, "-to", end,
                "-map", "0:a",
                "-map_metadata", "0",
                "-af", fade_filter,
                *aac_encode_args(bitrate=BEST_M4A_BITRATE, resample_48k=True),
                str(out),
            ])
            if cover:
                attach_cover_art(out, cover)
            return out
        finally:
            if cover:
                cover.unlink(missing_ok=True)
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
            *h265_video_args(),
            *aac_encode_args(bitrate=VIDEO_AAC_BITRATE, resample_48k=True),
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
        # -to is relative to output timeline when -ss is before -i; use -t for duration.
        args.extend(["-t", str(track.end_seconds - track.start_seconds)])

    metadata = cue_track_metadata_args(
        title=track.title,
        track_number=track.number,
        performer=sheet.performer,
        album_title=sheet.album_title,
    )

    if same_source:
        args.extend([*stream_copy_with_cover_args(), *metadata, str(out)])
    else:
        args.extend([
            "-vn",
            *aac_encode_args(bitrate=BEST_M4A_BITRATE, resample_48k=True),
            *metadata,
            str(out),
        ])

    run_ffmpeg(args)
    return out


def split_cue_file(cue_path: Path, *, same_source: bool) -> list[Path]:
    sheet = parse_cue(cue_path)
    outputs: list[Path] = []
    for track in sheet.tracks:
        out = split_cue_track(sheet, track, same_source=same_source, cue_dir=cue_path.parent)
        outputs.append(out)
    return outputs
