#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from discover import FileGroups, MediaType, collect_files
from ffmpeg_util import check_dependencies
from menus import (
    prompt_compress_preset,
    prompt_fades,
    prompt_for_type,
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
        start = prompt_time("Start time")
        end = prompt_time("End time")
        fades = prompt_fades()
        for path in files:
            try:
                print(f"\nTrimming: {path.name}")
                presets.trim_audio(path, start, end, fades=fades)
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
        "m4a": presets.to_m4a_vbr,
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

    handlers = {
        "h265_mp4": presets.to_h265_mp4,
        "extract_audio": presets.extract_audio,
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


def _run_gif(action: str, files: list[Path]) -> tuple[int, int]:
    ok = fail = 0
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

    if not any([groups.audio, groups.video, groups.gif, groups.cue]):
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
