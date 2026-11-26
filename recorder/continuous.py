"""Supervise independent FFmpeg recorders for four local RTSP streams."""

from __future__ import annotations

import argparse
import logging
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

LOG = logging.getLogger(__name__)
COURTS = tuple(f"court{i:02d}" for i in range(1, 5))
ARENA_ZONE = ZoneInfo("America/Fortaleza")


def new_session(root: Path, court: str) -> Path:
    now = datetime.now(UTC)
    day = now.astimezone(ARENA_ZONE).date().isoformat()
    session = root / court / day / f"{now:%Y%m%dT%H%M%S.%fZ}-{uuid4().hex[:8]}"
    session.mkdir(parents=True, exist_ok=False)
    return session


def ffmpeg_command(url: str, session: Path, segment_seconds: int) -> list[str]:
    if segment_seconds < 1:
        raise ValueError("segment_seconds must be positive")
    return [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "warning",
        "-rtsp_transport", "tcp", "-timeout", "5000000", "-i", url,
        "-map", "0:v:0", "-an", "-c:v", "copy",
        "-f", "segment", "-segment_format", "mpegts",
        "-segment_time", str(segment_seconds), "-reset_timestamps", "1",
        "-segment_list", str(session / "segments.csv"),
        "-segment_list_type", "csv", "-segment_list_size", "0",
        str(session / "%06d.ts"),
    ]


@dataclass
class Camera:
    court: str
    url: str
    process: subprocess.Popen | None = None
    retry_at: float = 0.0

    def tick(self, root: Path, segment_seconds: int, retry_seconds: float) -> None:
        now = time.monotonic()
        if self.process is not None:
            status = self.process.poll()
            if status is None:
                return
            LOG.warning("%s stopped (exit=%s); retrying in %.1fs", self.court, status, retry_seconds)
            self.process = None
            self.retry_at = now + retry_seconds
        if now < self.retry_at:
            return
        try:
            session = new_session(root, self.court)
            self.process = subprocess.Popen(
                ffmpeg_command(self.url, session, segment_seconds),
                start_new_session=True,
            )
            LOG.info("%s recording session: %s", self.court, session)
        except OSError as exc:
            LOG.error("%s could not start: %s", self.court, exc)
            self.retry_at = now + retry_seconds


def shutdown(cameras: list[Camera]) -> None:
    active = [c.process for c in cameras if c.process is not None]
    for proc in active:
        if proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 8
    for proc in active:
        try:
            proc.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("storage/recordings"))
    parser.add_argument("--segment-seconds", type=int, default=60)
    parser.add_argument("--retry-seconds", type=float, default=3)
    parser.add_argument("--rtsp-base", default="rtsp://127.0.0.1:8554")
    args = parser.parse_args()
    if args.segment_seconds < 1 or args.retry_seconds < 1:
        parser.error("segment and retry durations must be at least 1 second")
    if shutil.which("ffmpeg") is None:
        parser.error("FFmpeg must be installed")
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cameras = [Camera(court, f"{args.rtsp_base.rstrip('/')}/{court}") for court in COURTS]
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not stopping:
            for camera in cameras:
                if stopping:
                    break
                camera.tick(root, args.segment_seconds, args.retry_seconds)
            time.sleep(0.25)
    finally:
        shutdown(cameras)
        LOG.info("Recorder stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
