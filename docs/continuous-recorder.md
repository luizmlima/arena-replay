# Continuous recorder v0.1

From the repository root, with MediaMTX and the camera simulator running:

```sh
uv run python -m recorder.continuous --segment-seconds 10
```

Ctrl+C stops all four recorder processes. The default segment target is 60 seconds.
Each camera has a separate FFmpeg process. RTSP/TCP uses a five-second socket
I/O timeout. Exited processes retry after three seconds. The capture copies
H.264 without encoding, discards audio, and writes MPEG-TS segments. Actual
segment boundaries depend on keyframes.

Layout: `storage/recordings/court01/YYYY-MM-DD/UTC-session-id/000000.ts`.
The date directory is the local date at connection start, not the date of every
frame. Unique session directories prevent overwrites on reconnect. The CSV
manifest records media-relative segment intervals, not exact wall-clock times.
The final segment may be shorter, and an abrupt interruption can truncate it.

This is a local prototype. No schedule, storage limits, retention, wall-clock
index, cross-segment exports, or public serving are implemented yet. Run only
one instance and stop it when done. Never serve the storage directory directly.

Tests: `uv run python -m pytest tests/test_continuous_recorder.py -v`.
