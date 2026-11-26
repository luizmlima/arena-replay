# Video engine — v0.1

Local processing for a single finite source video. Requires Python 3.12+, FFmpeg/FFprobe with libx264 and drawtext support, and pytest for tests. It does not require Docker, a database, cameras or a payment service.

From the repository root:

```sh
uv run python -m pytest -q
```

Example (requires the existing 30-second synthetic recording):

```python
from video_worker import ClipRange, export_highlights, generate_preview

source = "storage/recordings/test.mp4"
export_highlights(source, [ClipRange(5, 10), ClipRange(20, 25)],
                  "storage/exports/highlights_v1.mp4")
generate_preview(source, "storage/previews/test.mp4")
```

`export_clip` produces a standalone clip. `export_highlights` sorts non-overlapping selections by start time, encodes only selected intervals and concatenates them. Endpoints are expressed in seconds relative to the source. Audio is disabled. Output is H.264 MP4 with fast start and yuv420p. Cuts are constrained by frame timing. Re-encoding can change image quality. Exports are published atomically after processing; an existing destination is replaced on success. The preview is at most 480 pixels high, with a static burned-in watermark and an 800 kbps video bitrate target. A watermark is a deterrent, not access control.

Current limits: one source file per export, overlapping ranges rejected, no RTSP, recording index, scheduling, cross-file cuts, payment, background queue, or authentication yet. Never expose local source paths or allow arbitrary destination paths in a public API. The future API must choose and authorize paths on the server. Test with real camera streams and the intended server before deployment.
