# permute

Interactive CLI that batch-converts media with ffmpeg. Point it at files or folders; it groups by extension and asks what to do with each group.

## Requirements

- Python 3
- [ffmpeg](https://ffmpeg.org/) on `PATH` (`brew install ffmpeg`)
- Python packages in `requirements.txt` (Pillow, pypdf, pymupdf) for image/PDF work

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python permute.py path/to/file.mp4
python permute.py ~/Downloads/album/
python permute.py clip.mov song.flac cover.png
```

Outputs land next to the source files. Unsupported extensions are skipped.

## What it can do

**Audio.** M4A 256k, MP3 VBR or 128k, trim (optional fades), split by duration, extract cover art.

**Video.** H.265 MP4, compress presets (10 MB / 1080p / 720p / 480p), extract audio, grab a frame as JPG, speed up, split by duration, combine multiple videos.

**Image.** Best JPG, or several images into one PDF.

**PDF.** Rasterize to JPG pages, or combine PDFs.

**GIF.** Convert to H.265 MP4, optimize, or extract a frame.

**CUE.** Split the referenced audio into tracks (same format as source, or best M4A).
