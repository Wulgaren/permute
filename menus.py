from __future__ import annotations

from discover import MediaType


def _prompt_choice(options: list[str], label: str) -> int | None:
    print(f"\n{label}")
    for i, option in enumerate(options, start=1):
        print(f"  {i}) {option}")
    print("  0) Skip")

    while True:
        raw = input("Choice: ").strip()
        if raw == "0":
            return None
        if raw.isdigit():
            choice = int(raw)
            if 1 <= choice <= len(options):
                return choice
        print("Invalid choice, try again.")


def _format_file_list(files: list, limit: int = 3) -> str:
    names = [f.name for f in files]
    if len(names) <= limit:
        return ", ".join(names)
    shown = ", ".join(names[:limit])
    return f"{shown}, +{len(names) - limit} more"


def prompt_audio_action(files: list) -> str | None:
    choice = _prompt_choice(
        [
            "Best M4A (VBR)",
            "Best MP3 (VBR)",
            "MP3 128 kbps",
            "Trim audio",
            "Split by duration",
        ],
        f"Audio files ({len(files)}): {_format_file_list(files)}",
    )
    actions = ["m4a", "mp3_vbr", "mp3_128", "trim", "split"]
    return actions[choice - 1] if choice else None


def prompt_video_action(files: list, *, can_combine: bool) -> str | None:
    options = [
        "Best MP4 (H.265)",
        "Extract audio (best M4A)",
        "Speed up",
        "Split by duration",
    ]
    if can_combine:
        options.append("Combine videos")

    choice = _prompt_choice(
        options,
        f"Video files ({len(files)}): {_format_file_list(files)}",
    )
    if not choice:
        return None

    actions = ["h265_mp4", "extract_audio", "speed_up", "split"]
    if can_combine:
        actions.append("combine")
    return actions[choice - 1]


def prompt_speed() -> float | None:
    choice = _prompt_choice(
        ["1.5x", "2x", "2.5x", "3x"],
        "Speed factor",
    )
    speeds = [1.5, 2.0, 2.5, 3.0]
    return speeds[choice - 1] if choice else None


def prompt_gif_action(files: list) -> str | None:
    choice = _prompt_choice(
        [
            "Convert to MP4 (H.265)",
            "Optimize GIF",
        ],
        f"GIF files ({len(files)}): {_format_file_list(files)}",
    )
    actions = ["to_mp4", "optimize"]
    return actions[choice - 1] if choice else None


def prompt_cue_action(files: list) -> str | None:
    choice = _prompt_choice(
        [
            "Split (same as source)",
            "Split (best M4A VBR)",
        ],
        f"CUE files ({len(files)}): {_format_file_list(files)}",
    )
    actions = ["split_source", "split_m4a"]
    return actions[choice - 1] if choice else None


def prompt_minutes() -> float:
    while True:
        raw = input("Minutes per split: ").strip()
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
        print("Enter a positive number.")


def prompt_time(label: str) -> str:
    while True:
        raw = input(f"{label}: ").strip()
        if raw:
            return raw
        print("Required.")


def prompt_fades() -> bool:
    while True:
        raw = input("Add fade in/out? (y/n): ").strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Enter y or n.")


def prompt_for_type(media_type: MediaType, files: list) -> str | None:
    if media_type is MediaType.AUDIO:
        return prompt_audio_action(files)
    if media_type is MediaType.VIDEO:
        return prompt_video_action(files, can_combine=len(files) >= 2)
    if media_type is MediaType.GIF:
        return prompt_gif_action(files)
    if media_type is MediaType.CUE:
        return prompt_cue_action(files)
    return None
