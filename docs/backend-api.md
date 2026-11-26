# Local HTTP API v0.1

Run from the repository root with the existing uv environment:

```sh
uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs for interactive Swagger documentation.
Stop with Ctrl+C. Use previously completed recording sessions; the recorder can remain stopped.

## Endpoints

- `GET /api/health` — HTTP service health, not camera health.
- `GET /api/courts` — four court identifiers.
- `GET /api/courts/{court}/recordings?day=2026-11-26` — local-day intervals; `day` is optional. No source paths are exposed.
- `POST /api/courts/{court}/quote` — validate coverage and return integer cents. Example JSON:
  ```json
  {"mode":"replay","ranges":[{"start":"2026-11-25T23:59:53-03:00","end":"2026-11-26T00:00:13-03:00"},{"start":"2026-11-26T00:00:33-03:00","end":"2026-11-26T00:00:43-03:00"}]}
  ```
- `POST /api/courts/{court}/preview` — generate a watermarked MP4 (maximum 60 seconds per request). Example JSON:
  ```json
  {"start":"2026-11-25T23:59:53-03:00","end":"2026-11-26T00:00:13-03:00"}
  ```
- `GET /api/previews/{identifier}` — serve only the generated preview; append the returned relative URL to the local server address to play.

## Rules and limitations

Replay prices are 500 cents/minute, prorated by time, rounded half-up to cents with a provisional 500-cent minimum per order. Full-hour mode is 5000 cents for one fully covered, clock-aligned hour. Selections require offsets, non-overlap, full coverage and at least one second per interval. Prototype maximum: 30 intervals and 60 minutes total for replay. No automatic change to the full-hour product.

The timestamps remain estimates. This module reads stopped sessions from the existing file-based catalog, without a database. One preview can be generated concurrently per process; the synchronous two-pass preview process is intended for development only. Preview files remain in `storage/previews/api` until manually removed. It is not a scalable live timeline, payment system, or production security solution. No original or unwatermarked file is available over HTTP. Do not expose this server to other networks or the public internet; a public deployment requires authorization rules for images, limits, retention, production job management and secure delivery.

Run tests with `uv run python -m pytest -v`.
