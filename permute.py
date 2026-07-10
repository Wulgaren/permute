#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from discover import FileGroups, MediaType, collect_files
from ffmpeg_util import check_dependencies
from ffmpeg_util import probe_audio_streams
from menus import (
    prompt_audio_track,
    prompt_compress_preset,
    prompt_fade_in,
    prompt_fade_out,
    prompt_for_type,
    prompt_frame_number,
    prompt_minutes,
    prompt_speed,
    prompt_time,
)
import presets


def _print_skipped(groups: FileGroups) -> None:
    if groups.skipped:
        print(f"Skipped {len(groups.skipped)} unsupported file(s).")


def _run_audio(action: str, files: list[Path]) -> tuple[int, int]:
    ok = fail = 0

    if action == "trim":
        start = prompt_time("Start time (HH:MM:SS)")
        end = prompt_time("End time (HH:MM:SS)")
        fade_in = prompt_fade_in()
        fade_out = prompt_fade_out()
        for path in files:
            try:
                print(f"\nTrimming: {path.name}")
                presets.trim_audio(path, start, end, fade_in=fade_in, fade_out=fade_out)
                ok += 1
            except Exception as exc:
                print(f"  Failed: {exc}")
                fail += 1
        return ok, fail

    if action == "split":
        minutes = prompt_minutes()
        for path in files:
            try:
                print(f"\nSplitting: {path.name}")
                parts = presets.split_by_duration(path, minutes)
                print(f"  Created {len(parts)} part(s)")
                ok += 1
            except Exception as exc:
                print(f"  Failed: {exc}")
                fail += 1
        return ok, fail

    handlers = {
        "m4a": presets.to_m4a,
        "mp3_vbr": presets.to_mp3_vbr,
        "mp3_128": presets.to_mp3_128,
    }
    handler = handlers[action]
    for path in files:
        try:
            print(f"\nConverting: {path.name}")
            out = handler(path)
            print(f"  -> {out.name}")
            ok += 1
        except Exception as exc:
            print(f"  Failed: {exc}")
            fail += 1
    return ok, fail


def _run_video(action: str, files: list[Path]) -> tuple[int, int]:
    ok = fail = 0

    if action == "combine":
        try:
            print(f"\nCombining {len(files)} video(s)")
            out = presets.combine_videos(files)
            print(f"  -> {out.name}")
            return 1, 0
        except Exception as exc:
            print(f"  Failed: {exc}")
            return 0, 1

    if action == "speed_up":
        speed = prompt_speed()
        if speed is None:
            return 0, 0
        for path in files:
            try:
                print(f"\nSpeeding up ({speed}x): {path.name}")
                out = presets.speed_up_video(path, speed)
                print(f"  -> {out.name}")
                ok += 1
            except Exception as exc:
                print(f"  Failed: {exc}")
                fail += 1
        return ok, fail

    if action == "split":
        minutes = prompt_minutes()
        for path in files:
            try:
                print(f"\nSplitting: {path.name}")
                parts = presets.split_by_duration(path, minutes)
                print(f"  Created {len(parts)} part(s)")
                ok += 1
            except Exception as exc:
                print(f"  Failed: {exc}")
                fail += 1
        return ok, fail

    if action == "compress":
        preset = prompt_compress_preset()
        if preset is None:
            return 0, 0
        for path in files:
            try:
                print(f"\nCompressing ({preset.name}): {path.name}")
                out = presets.compress_video(path, preset)
                print(f"  -> {out.name}")
                ok += 1
            except Exception as exc:
                print(f"  Failed: {exc}")
                fail += 1
        return ok, fail

    if action == "frame_jpg":
        frame_number = prompt_frame_number()
        frame_index = frame_number - 1
        for path in files:
            try:
                print(f"\nExtracting frame {frame_number}: {path.name}")
                out = presets.video_frame_jpg(path, frame_index=frame_index)
                print(f"  -> {out.name}")
                ok += 1
            except Exception as exc:
                print(f"  Failed: {exc}")
                fail += 1
        return ok, fail

    if action == "extract_audio":
        audio_stream: int | None = None
        streams = probe_audio_streams(files[0])
        if len(streams) > 1:
            picked = prompt_audio_track(streams)
            if picked is None:
                return 0, 0
            audio_stream = picked

        for path in files:
            try:
                if audio_stream is not None:
                    path_streams = probe_audio_streams(path)
                    if audio_stream >= len(path_streams):
                        raise RuntimeError(
                            f"Track {audio_stream + 1} not found "
                            f"({len(path_streams)} audio track(s) available)"
                        )
                print(f"\nConverting: {path.name}")
                out = presets.extract_audio(path, audio_stream=audio_stream)
                print(f"  -> {out.name}")
                ok += 1
            except Exception as exc:
                print(f"  Failed: {exc}")
                fail += 1
        return ok, fail

    handlers = {
        "h265_mp4": presets.to_h265_mp4,
    }
    handler = handlers[action]
    for path in files:
        try:
            print(f"\nConverting: {path.name}")
            out = handler(path)
            print(f"  -> {out.name}")
            ok += 1
        except Exception as exc:
            print(f"  Failed: {exc}")
            fail += 1
    return ok, fail


def _run_image(action: str, files: list[Path]) -> tuple[int, int]:
    ok = fail = 0

    if action == "to_pdf":
        try:
            print(f"\nConverting {len(files)} image(s) to PDF")
            out = presets.images_to_pdf(files)
            print(f"  -> {out.name}")
            return 1, 0
        except Exception as exc:
            print(f"  Failed: {exc}")
            return 0, 1

    for path in files:
        try:
            print(f"\nConverting: {path.name}")
            out = presets.to_best_jpg(path)
            print(f"  -> {out.name}")
            ok += 1
        except Exception as exc:
            print(f"  Failed: {exc}")
            fail += 1
    return ok, fail


def _run_pdf(action: str, files: list[Path]) -> tuple[int, int]:
    ok = fail = 0

    if action == "combine":
        try:
            print(f"\nCombining {len(files)} PDF(s)")
            out = presets.combine_pdfs(files)
            print(f"  -> {out.name}")
            return 1, 0
        except Exception as exc:
            print(f"  Failed: {exc}")
            return 0, 1

    for path in files:
        try:
            print(f"\nConverting: {path.name}")
            outputs = presets.pdf_to_jpg(path)
            for out in outputs:
                print(f"  -> {out.name}")
            ok += 1
        except Exception as exc:
            print(f"  Failed: {exc}")
            fail += 1
    return ok, fail


def _run_gif(action: str, files: list[Path]) -> tuple[int, int]:
    ok = fail = 0

    if action == "frame_jpg":
        frame_number = prompt_frame_number()
        frame_index = frame_number - 1
        for path in files:
            try:
                print(f"\nExtracting frame {frame_number}: {path.name}")
                out = presets.video_frame_jpg(path, frame_index=frame_index)
                print(f"  -> {out.name}")
                ok += 1
            except Exception as exc:
                print(f"  Failed: {exc}")
                fail += 1
        return ok, fail

    handlers = {
        "to_mp4": presets.gif_to_mp4,
        "optimize": presets.optimize_gif,
    }
    handler = handlers[action]
    for path in files:
        try:
            print(f"\nConverting: {path.name}")
            out = handler(path)
            print(f"  -> {out.name}")
            ok += 1
        except Exception as exc:
            print(f"  Failed: {exc}")
            fail += 1
    return ok, fail


def _run_cue(action: str, files: list[Path]) -> tuple[int, int]:
    ok = fail = 0
    same_source = action == "split_source"
    for path in files:
        try:
            print(f"\nSplitting CUE: {path.name}")
            tracks = presets.split_cue_file(path, same_source=same_source)
            print(f"  Created {len(tracks)} track(s)")
            ok += 1
        except Exception as exc:
            print(f"  Failed: {exc}")
            fail += 1
    return ok, fail


def process_groups(groups: FileGroups) -> tuple[int, int]:
    total_ok = total_fail = 0
    type_groups = [
        (MediaType.AUDIO, groups.audio),
        (MediaType.VIDEO, groups.video),
        (MediaType.IMAGE, groups.image),
        (MediaType.PDF, groups.pdf),
        (MediaType.GIF, groups.gif),
        (MediaType.CUE, groups.cue),
    ]

    for media_type, files in type_groups:
        if not files:
            continue

        action = prompt_for_type(media_type, files)
        if not action:
            print("Skipped.")
            continue

        if media_type is MediaType.AUDIO:
            ok, fail = _run_audio(action, files)
        elif media_type is MediaType.VIDEO:
            ok, fail = _run_video(action, files)
        elif media_type is MediaType.IMAGE:
            ok, fail = _run_image(action, files)
        elif media_type is MediaType.PDF:
            ok, fail = _run_pdf(action, files)
        elif media_type is MediaType.GIF:
            ok, fail = _run_gif(action, files)
        elif media_type is MediaType.CUE:
            ok, fail = _run_cue(action, files)
        else:
            continue

        total_ok += ok
        total_fail += fail

    return total_ok, total_fail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert media files with ffmpeg — interactive menus per file type.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Files or folders to process",
    )
    args = parser.parse_args(argv)

    check_dependencies()
    groups = collect_files(args.paths)

    if not any([groups.audio, groups.video, groups.image, groups.pdf, groups.gif, groups.cue]):
        _print_skipped(groups)
        print("No supported media files found.")
        return 1

    _print_skipped(groups)
    ok, fail = process_groups(groups)

    total = ok + fail
    if total:
        print(f"\nDone: {ok}/{total} succeeded" + (f" ({fail} failed)" if fail else ""))
    else:
        print("\nNothing processed.")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
