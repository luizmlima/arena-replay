"""Local video processing; no web, payment or camera dependencies."""

import json
import subprocess
from collections.abc import Iterable
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory

from .exceptions import InvalidSelectionError, VideoProcessingError
from .models import ClipRange, VideoInfo


def _run(*args: str) -> str:
    try:
        result = subprocess.run(args, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise VideoProcessingError(f"Required executable not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise VideoProcessingError(exc.stderr.strip() or str(exc)) from exc
    return result.stdout


def probe_video(source: str | Path) -> VideoInfo:
    path = Path(source).resolve()
    if not path.is_file():
        raise VideoProcessingError(f"Source file not found: {path}")
    raw = _run(
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=duration,width,height,codec_name:format=duration",
        "-of", "json", str(path),
    )
    try:
        data = json.loads(raw)
        stream = data["streams"][0]
        duration = stream.get("duration")
        if duration in (None, "N/A"):
            duration = data["format"]["duration"]
        duration = float(duration)
        if not isfinite(duration) or duration <= 0:
            raise ValueError("Invalid duration")
        return VideoInfo(duration, stream["width"], stream["height"], stream["codec_name"])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise VideoProcessingError("Unable to determine video properties.") from exc


def _validate_ranges(clips: Iterable[ClipRange], duration: float) -> list[ClipRange]:
    ordered = sorted(clips, key=lambda clip: clip.start)
    if not ordered:
        raise InvalidSelectionError("Select at least one clip.")
    for index, clip in enumerate(ordered):
        if clip.end > duration:
            raise InvalidSelectionError("Clip extends beyond the source video.")
        if index and clip.start < ordered[index - 1].end:
            raise InvalidSelectionError("Selected clips must not overlap.")
    return ordered


def _encode_clip(source: Path, clip: ClipRange, destination: Path) -> None:
    _run(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-nostdin", "-y",
        "-ss", str(clip.start), "-i", str(source), "-t", str(clip.duration),
        "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(destination),
    )


def export_highlights(
    source: str | Path, clips: Iterable[ClipRange], destination: str | Path,
) -> Path:
    """Encode clips in chronological order and concatenate them into one silent MP4.

    Existing destination files are replaced only after successful processing.
    The source must be one finite video file (not an RTSP stream).
    Cuts are limited by frame timing; the source resolution is retained if even.
    """
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if source == destination:
        raise InvalidSelectionError("Destination must not be the source video.")
    if destination.suffix.lower() != ".mp4":
        raise InvalidSelectionError("Destination must be an MP4 file.")
    ordered = _validate_ranges(clips, probe_video(source).duration)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="replay-", dir=destination.parent) as directory:
        work = Path(directory)
        names = []
        for index, clip in enumerate(ordered):
            name = f"clip_{index:04d}.mp4"
            _encode_clip(source, clip, work / name)
            names.append(name)
        if len(names) == 1:
            final = work / names[0]
        else:
            manifest = work / "concat.txt"
            manifest.write_text("".join(f"file '{name}'\n" for name in names), encoding="utf-8")
            final = work / "result.mp4"
            _run(
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-nostdin", "-y",
                "-f", "concat", "-safe", "1", "-i", str(manifest),
                "-map", "0:v:0", "-c", "copy", "-movflags", "+faststart", str(final),
            )
        probe_video(final)
        final.replace(destination)
    return destination


def export_clip(source: str | Path, clip: ClipRange, destination: str | Path) -> Path:
    """Export a single selection using the same validation and encoding pipeline."""
    return export_highlights(source, [clip], destination)


def generate_preview(source: str | Path, destination: str | Path) -> Path:
    """Create a reusable low-resolution preview with a burned-in static watermark."""
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if source == destination or destination.suffix.lower() != ".mp4":
        raise InvalidSelectionError("Preview must be a different MP4 file.")
    probe_video(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    video_filter = (
        "scale=-2:'min(480,trunc(ih/2)*2)',"
        "drawtext=text='ARENA REPLAY - PREVIEW':fontcolor=white@0.65:"
        "fontsize=h/14:box=1:boxcolor=black@0.35:boxborderw=5:"
        "x=(w-tw)/2:y=(h-th)/2"
    )
    with TemporaryDirectory(prefix="preview-", dir=destination.parent) as directory:
        final = Path(directory) / "preview.mp4"
        _run(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-nostdin", "-y",
            "-i", str(source), "-map", "0:v:0", "-an", "-sn", "-dn", "-vf", video_filter,
            "-c:v", "libx264", "-preset", "fast", "-b:v", "800k", "-maxrate", "800k",
            "-bufsize", "1600k", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(final),
        )
        probe_video(final)
        final.replace(destination)
    return destination
