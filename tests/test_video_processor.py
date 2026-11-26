import subprocess
from pathlib import Path

import pytest

from video_worker import (
    ClipRange, InvalidSelectionError, VideoProcessingError,
    export_clip, export_highlights, generate_preview, probe_video,
)


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("video") / "source.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=red:size=640x540:rate=25:duration=2",
        "-f", "lavfi", "-i", "color=blue:size=640x540:rate=25:duration=2",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ], check=True)
    return path


def pixel_at(path: Path, timestamp: float) -> tuple[int, int, int]:
    data = subprocess.check_output([
        "ffmpeg", "-v", "error", "-ss", str(timestamp), "-i", str(path),
        "-frames:v", "1", "-vf", "scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
    ])
    return tuple(data[:3])


def test_probe(source: Path) -> None:
    info = probe_video(source)
    assert info.duration == pytest.approx(4, abs=0.04)
    assert (info.width, info.height, info.codec) == (640, 540, "h264")


def test_export_clip(source: Path, tmp_path: Path) -> None:
    out = export_clip(source, ClipRange(0.4, 1.4), tmp_path / "single.mp4")
    assert probe_video(out).duration == pytest.approx(1, abs=0.04)


def test_highlights_duration_and_chronology(source: Path, tmp_path: Path) -> None:
    out = export_highlights(source, [ClipRange(2.4, 3.4), ClipRange(0.4, 1.4)],
                            tmp_path / "highlights.mp4")
    assert probe_video(out).duration == pytest.approx(2, abs=0.08)
    red = pixel_at(out, 0.4)
    blue = pixel_at(out, 1.4)
    assert red[0] > 200 and red[2] < 60
    assert blue[2] > 200 and blue[0] < 60
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(out), "-f", "null", "-"],
                   check=True)


@pytest.mark.parametrize("start,end", [(-1, 2), (2, 1), (1, 1), (float("nan"), 2)])
def test_invalid_clip(start: float, end: float) -> None:
    with pytest.raises(InvalidSelectionError):
        ClipRange(start, end)


@pytest.mark.parametrize("clips", [[], [ClipRange(3, 5)], [ClipRange(0, 2), ClipRange(1, 3)]])
def test_invalid_selection(source: Path, tmp_path: Path, clips: list[ClipRange]) -> None:
    out = tmp_path / "invalid.mp4"
    with pytest.raises(InvalidSelectionError):
        export_highlights(source, clips, out)
    assert not out.exists()


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(VideoProcessingError):
        probe_video(tmp_path / "missing.mp4")


def test_source_not_overwritten(source: Path) -> None:
    with pytest.raises(InvalidSelectionError):
        export_clip(source, ClipRange(0, 1), source)
    assert probe_video(source).duration == pytest.approx(4)


def test_preview(source: Path, tmp_path: Path) -> None:
    out = generate_preview(source, tmp_path / "preview.mp4")
    info = probe_video(out)
    assert info.height == 480
    assert info.duration == pytest.approx(4, abs=0.08)
