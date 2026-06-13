# permute

Interactive terminal media converter powered by ffmpeg.

## Requirements

- Python 3.10+
- ffmpeg / ffprobe (`brew install ffmpeg`)

## Usage

```bash
python permute.py /path/to/file.mp3
python permute.py /path/to/folder
python permute.py song.flac video.mkv album.cue
```

Pass files and/or folders (folders are scanned recursively). Unsupported files (images, etc.) are skipped. You get one numbered menu per media type — pick once, it applies to all files of that type.

Original files are never deleted. Outputs are saved next to the originals.

## Menus

### Audio
1. Best M4A (VBR)
2. Best MP3 (VBR)
3. MP3 128 kbps
4. Trim audio — prompts start/end times; optional fade in/out
5. Split by duration — prompts minutes per split

### Video
1. Best MP4 (H.265)
2. Extract audio (best M4A)
3. Split by duration
4. Combine videos (only when 2+ videos in batch)

### GIF
1. Convert to MP4 (H.265)
2. Optimize GIF

### CUE
1. Split (same as source codec)
2. Split (best M4A VBR)

## Output naming

- **Different extension** → same basename: `song.flac` → `song.m4a`
- **Same extension** → suffix added: `song.mp3` → `song_128k.mp3`, `clip.mp4` → `clip_h265.mp4`
- **Duration split** → `movie_part01.mp4`, `movie_part02.mp4`, …
- **CUE split** → `01 - Title.ext`, `02 - Title.ext`, …

## Notes

- Stream-copy operations (trim, split) are fast and lossless but may cut on nearest keyframe — parts can be off by a few seconds.
- Embedded cover art is preserved on all split parts and stream-copy trims.
- Fade in/out requires re-encoding and produces a new file with `_fade` suffix.
- Combined videos are saved as `combined.mp4` next to the first input video.
