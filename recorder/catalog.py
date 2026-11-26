"""Read completed recording manifests and export timestamp-selected replays."""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory

from recorder.continuous import ARENA_ZONE, COURTS
from video_worker import probe_video


class CatalogError(ValueError):
    """Invalid catalog, missing coverage, or failed export."""


@dataclass(frozen=True)
class Segment:
    path: Path
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Piece:
    segment: Segment
    start: float
    end: float


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CatalogError("Timestamp must include a UTC offset.")
    return value.astimezone(UTC)


def _video_timing(path: Path) -> tuple[float, float]:
    """Read video stream start PTS and duration (seconds), not container offsets."""
    try:
        output = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=start_time,duration", "-of", "json", str(path)],
            check=True, capture_output=True, text=True,
        )
        stream = json.loads(output.stdout)["streams"][0]
        start, duration = float(stream["start_time"]), float(stream["duration"])
        if not (isfinite(start) and isfinite(duration) and duration > 0):
            raise ValueError("invalid video timing")
        return start, duration
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise CatalogError(f"Cannot read segment timing: {path}") from exc


def _first_segment_begin(rows: list[tuple[Path, float, float]]) -> float:
    """Exclude a startup PTS offset only when the next segment corroborates it."""
    path, begin, end = rows[0]
    if begin != 0 or not _usable(path):
        return begin
    pts, duration = _video_timing(path)
    deficit = end - begin - duration
    tolerance = 0.05  # timestamp/frame rounding; not the export duration tolerance
    if abs(deficit) <= tolerance:
        return begin
    if deficit > 0 and len(rows) > 1:
        next_path, next_begin, next_end = rows[1]
        if abs(next_begin - end) <= 0.000002 and _usable(next_path):
            next_pts, next_duration = _video_timing(next_path)
            if (abs((pts - next_pts) - deficit) <= tolerance
                    and abs(next_end - next_begin - next_duration) <= tolerance):
                return end - duration
    raise CatalogError(f"Unverified startup timestamp discrepancy: {path}")


def _usable(path: Path) -> bool:
    return path.is_file() and not path.is_symlink() and path.stat().st_size > 0


def load_catalog(root: str | Path, court: str) -> list[Segment]:
    """Read stopped sessions; wall time is estimated from process-start UTC."""
    if court not in COURTS:
        raise CatalogError(f"Unknown court: {court}")
    result = []
    court_dir = Path(root).resolve() / court
    for manifest in sorted(court_dir.glob("*/*/segments.csv")):
        try:
            stamp, suffix = manifest.parent.name.rsplit("-", 1)
            if not re.fullmatch(r"[0-9a-f]{8}", suffix):
                raise ValueError("invalid session ID")
            anchor = datetime.strptime(stamp, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=UTC)
            rows = []
            with manifest.open(newline="", encoding="utf-8") as file:
                for name, begin, end in csv.reader(file, strict=True):
                    if not re.fullmatch(r"[0-9]+\.ts", name):
                        raise ValueError("invalid segment filename")
                    a, b = float(begin), float(end)
                    if not (isfinite(a) and isfinite(b) and 0 <= a < b):
                        raise ValueError("invalid segment interval")
                    rows.append((manifest.parent / name, a, b))
            if rows:
                corrected_begin = _first_segment_begin(rows)
                rows[0] = (rows[0][0], corrected_begin, rows[0][2])
            for path, a, b in rows:
                if not _usable(path):
                    continue
                start, finish = anchor + timedelta(seconds=a), anchor + timedelta(seconds=b)
                if finish <= start:
                    raise ValueError("segment is shorter than timestamp precision")
                result.append(Segment(path, start, finish))
        except (OSError, ValueError, csv.Error, OverflowError) as exc:
            raise CatalogError(f"Invalid manifest {manifest}: {exc}") from exc
    return sorted(result, key=lambda item: (item.start, item.end, item.path))


def select_range(segments: list[Segment], start: datetime, end: datetime) -> list[Piece]:
    """Resolve a half-open wall-time interval; fail on gaps or ambiguous overlap."""
    start, end = utc(start), utc(end)
    if start >= end:
        raise CatalogError("Expected start < end.")
    cursor = start
    pieces = []
    for item in sorted(segments, key=lambda s: (s.start, s.end)):
        a, b = max(item.start, start), min(item.end, end)
        if a >= b:
            continue
        if a > cursor:
            raise CatalogError(f"Recording gap begins at {cursor.isoformat()}")
        if a < cursor:
            raise CatalogError(f"Ambiguous overlapping recordings at {a.isoformat()}")
        pieces.append(Piece(item, (a - item.start).total_seconds(), (b - item.start).total_seconds()))
        cursor = b
    if cursor < end:
        raise CatalogError(f"Recording gap begins at {cursor.isoformat()}")
    return pieces


def _run(*args: str) -> None:
    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CatalogError(getattr(exc, "stderr", None) or str(exc)) from exc


def export_ranges(segments: list[Segment], ranges: list[tuple[datetime, datetime]], destination: str | Path) -> Path:
    """Export chronological non-overlapping ranges to a silent 30 FPS MP4."""
    ordered = sorted((utc(a), utc(b)) for a, b in ranges)
    if not ordered:
        raise CatalogError("Select at least one range.")
    pieces = []
    for i, (start, end) in enumerate(ordered):
        if i and start < ordered[i - 1][1]:
            raise CatalogError("Selected ranges overlap.")
        pieces.extend(select_range(segments, start, end))
    destination = Path(destination).resolve()
    if destination.suffix.lower() != ".mp4":
        raise CatalogError("Destination must be an MP4 file.")
    if any(destination == s.path.resolve() for s in segments):
        raise CatalogError("Destination must not replace a source file.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="catalog-", dir=destination.parent) as tmp:
        work = Path(tmp)
        names = []
        first = probe_video(pieces[0].segment.path)
        dimensions = (first.width // 2 * 2, first.height // 2 * 2)
        for i, piece in enumerate(pieces):
            source = piece.segment.path
            info = probe_video(source)
            if (info.width // 2 * 2, info.height // 2 * 2) != dimensions:
                raise CatalogError("Resolution changed during selection; export one resolution at a time.")
            name = f"piece{i:05d}.mp4"
            output = work / name
            filters = (f"setpts=PTS-STARTPTS,trim=start={piece.start:.6f}:end={piece.end:.6f},"
                       f"setpts=PTS-STARTPTS,scale={dimensions[0]}:{dimensions[1]},fps=30")
            _run("ffmpeg", "-v", "error", "-xerror", "-nostdin", "-y", "-i", str(source),
                 "-map", "0:v:0", "-an", "-vf", filters, "-c:v", "libx264", "-preset", "fast",
                 "-crf", "20", "-pix_fmt", "yuv420p", str(output))
            actual = probe_video(output).duration
            if abs(actual - (piece.end - piece.start)) > 0.12:
                raise CatalogError(f"Decoded duration differs from manifest: {source}")
            names.append(name)
        manifest = work / "concat.txt"
        manifest.write_text("".join(f"file '{name}'\n" for name in names), encoding="utf-8")
        result = work / "result.mp4"
        _run("ffmpeg", "-v", "error", "-xerror", "-nostdin", "-y", "-f", "concat", "-safe", "1",
             "-i", str(manifest), "-map", "0:v:0", "-c", "copy", "-movflags", "+faststart", str(result))
        probe_video(result)
        result.replace(destination)
    return destination


def parse_timestamp(value: str) -> datetime:
    try:
        return utc(datetime.fromisoformat(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use ISO timestamp with offset, e.g. 2026-11-25T19:00:05-03:00") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("list", "export"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--root", type=Path, default=Path("storage/recordings"))
        cmd.add_argument("--court", choices=COURTS, required=True)
        if action == "export":
            cmd.add_argument("--range", nargs=2, action="append", required=True, type=parse_timestamp, metavar=("START", "END"))
            cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        segments = load_catalog(args.root, args.court)
        if args.action == "list":
            for item in segments:
                print(f"{item.start.astimezone(ARENA_ZONE).isoformat(timespec='microseconds')} -> "
                      f"{item.end.astimezone(ARENA_ZONE).isoformat(timespec='microseconds')}  {item.path.name}")
            print(f"{len(segments)} segments (estimated wall-clock timestamps)")
        else:
            print(export_ranges(segments, args.range, args.output))
    except (CatalogError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Catalog error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
