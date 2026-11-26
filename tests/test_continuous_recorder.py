import csv
import shutil
import subprocess
from unittest.mock import Mock, patch

import pytest

from recorder.continuous import Camera, COURTS, ffmpeg_command, new_session, shutdown


def test_four_distinct_courts():
    assert COURTS == ("court01", "court02", "court03", "court04")


def test_session_paths_are_unique(tmp_path):
    first = new_session(tmp_path, "court01")
    second = new_session(tmp_path, "court01")
    assert first != second
    assert first.is_dir() and second.is_dir()
    assert first.parent.parent.name == "court01"


def test_invalid_segment_duration(tmp_path):
    with pytest.raises(ValueError):
        ffmpeg_command("rtsp://localhost/court01", tmp_path, 0)


def test_restart_after_failure(tmp_path):
    camera = Camera("court01", "rtsp://localhost/court01")
    first = Mock()
    first.poll.return_value = 1
    second = Mock()
    with patch("recorder.continuous.subprocess.Popen", side_effect=[first, second]) as launch:
        with patch("recorder.continuous.time.monotonic", side_effect=[1, 2, 3, 5]):
            camera.tick(tmp_path, 10, 3)
            camera.tick(tmp_path, 10, 3)
            camera.tick(tmp_path, 10, 3)
            assert launch.call_count == 1
            camera.tick(tmp_path, 10, 3)
            assert launch.call_count == 2
    assert camera.process is second


def test_shutdown_signals_child():
    camera = Camera("court01", "rtsp://localhost/court01")
    camera.process = Mock()
    camera.process.poll.return_value = None
    shutdown([camera])
    camera.process.send_signal.assert_called_once()
    camera.process.wait.assert_called_once()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_real_segment_muxer(tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10",
        "-t", "3", "-c:v", "libx264", "-g", "10", "-keyint_min", "10", "-sc_threshold", "0", str(source)
    ], check=True)
    session = new_session(tmp_path, "court01")
    command = ffmpeg_command("rtsp://localhost/court01", session, 1)
    # Replace only RTSP input options with a local test file; keep production muxing options.
    start = command.index("-rtsp_transport")
    end = command.index("-map")
    command[start:end] = ["-i", str(source)]
    subprocess.run(command, check=True)
    segments = sorted(session.glob("*.ts"))
    assert len(segments) == 3
    with (session / "segments.csv").open() as manifest:
        rows = list(csv.reader(manifest))
    assert len(rows) == len(segments)
    for path in segments:
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True)
