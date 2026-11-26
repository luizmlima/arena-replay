# Recording catalog v0.2

Run from repository root with the recorder stopped. No new Python dependencies.

```sh
uv run python -m recorder.catalog list --court court01
uv run python -m recorder.catalog export --court court01 \
  --range 2026-11-25T23:59:51-03:00 2026-11-26T00:00:01-03:00 \
  --output storage/exports/catalog_test.mp4
```

Use actual times from `list`. Repeat `--range START END` for multiple highlights;
all ranges must be on the same court. The catalog reads existing CSV manifests,
ignores empty session directories and missing/empty segment files, and sorts by
UTC. It rejects gaps, overlaps, malformed manifests and invalid timestamps.
Dates in the session directory are not used to compute segment times; this
allows a session to cross midnight. CLI displays America/Fortaleza time.

Important: absolute wall-clock times are estimates (session creation UTC plus
CSV media-relative offsets). Connection latency, camera buffering, clock drift
and GOP alignment can shift them. Before commercial use we must persist a
capture-time anchor and validate it against real cameras; the exact sports
moment is not guaranteed by this catalog. Do not use while recording or during
retention cleanup. No database, schedule, retention, protected streaming or
payment integration yet.

Export re-encodes each selected piece with H.264, yuv420p, 30 fps, no audio,
retaining the source dimensions (rounded to even). It concatenates pieces
chronologically and atomically replaces the output on success. It rejects
resolution changes and significant duration discrepancies. Cuts are limited
by frame timing; very short fragments can fail rather than silently disappear.
A long export may accumulate per-piece frame rounding and consume significant
CPU/disk. Validate 60-minute exports on the target hardware before production.

Tests: `uv run python -m pytest -v`. The suite includes real MPEG-TS creation,
cutting across segments, compilation, decoding and midnight handling.

## RTSP startup timestamp correction

The first CSV segment may include a startup offset before its first frame.
The catalog compares its stream duration and start PTS with the next segment.
When both corroborate the offset, only the first segment start is advanced;
its end and later boundaries remain unchanged. The original CSV is untouched.
An unverified discrepancy (including when no second segment exists) fails
closed rather than inventing footage. The wall-clock anchor is still estimated.
This version is for stopped sessions only.
