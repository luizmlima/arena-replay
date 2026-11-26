"""Local-only API prototype. Do not expose to the public internet."""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Literal
from uuid import UUID, uuid4
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from recorder.catalog import CatalogError, export_ranges, load_catalog, select_range, utc
from recorder.continuous import ARENA_ZONE, COURTS
from video_worker import generate_preview

log = logging.getLogger(__name__)


class TimeRange(BaseModel):
    start: datetime
    end: datetime


class QuoteRequest(BaseModel):
    mode: Literal['replay', 'full_hour'] = 'replay'
    ranges: list[TimeRange] = Field(min_length=1, max_length=30)


def create_app(storage: Path = Path('storage')) -> FastAPI:
    app = FastAPI(title='Arena Replay', version='0.1.0', description='Local prototype; no payment or original downloads.')
    storage = Path(storage).resolve()
    previews = storage / 'previews' / 'api'
    preview_lock = Lock()

    def catalog(court: str):
        if court not in COURTS:
            raise HTTPException(404, 'Unknown court')
        try:
            return load_catalog(storage / 'recordings', court)
        except (CatalogError, OSError):
            log.exception('Catalog unavailable')
            raise HTTPException(503, 'Recording catalog unavailable') from None

    def validate(segments, ranges):
        try:
            ordered = sorted((utc(r.start), utc(r.end)) for r in ranges)
            for index, (start, end) in enumerate(ordered):
                if end - start < timedelta(seconds=1):
                    raise CatalogError('Each range must be at least one second.')
                if index and start < ordered[index - 1][1]:
                    raise CatalogError('Selected ranges overlap.')
                select_range(segments, start, end)
            return ordered
        except (ValueError, OverflowError) as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    @app.get('/api/courts')
    def courts():
        return [{'id': court, 'name': f'Quadra {i:02d}'} for i, court in enumerate(COURTS, 1)]

    @app.get('/api/courts/{court}/recordings')
    def recordings(court: str, day: date | None = None):
        segments = catalog(court)
        intervals = []
        for segment in segments:
            start = segment.start.astimezone(ARENA_ZONE)
            end = segment.end.astimezone(ARENA_ZONE)
            if day is not None:
                begin = datetime.combine(day, datetime.min.time(), ARENA_ZONE)
                finish = begin + timedelta(days=1)
                start, end = max(start, begin), min(end, finish)
                if start >= end:
                    continue
            intervals.append({'start': start.isoformat(), 'end': end.isoformat()})
        return {'court': court, 'estimated_timestamps': True, 'segments': intervals}

    @app.post('/api/courts/{court}/quote')
    def quote(court: str, request: QuoteRequest):
        ordered = validate(catalog(court), request.ranges)
        elapsed = sum((end - start for start, end in ordered), timedelta())
        micros = elapsed // timedelta(microseconds=1)
        if request.mode == 'full_hour':
            start = ordered[0][0].astimezone(ARENA_ZONE)
            if len(ordered) != 1 or elapsed != timedelta(hours=1) or start.minute or start.second or start.microsecond:
                raise HTTPException(422, 'Full hour must be one complete clock-hour block.')
            cents = 5000
        else:
            if elapsed > timedelta(hours=1):
                raise HTTPException(422, 'Replay selections are limited to 60 minutes in this prototype.')
            cents = max(500, int((Decimal(micros) * 500 / 60_000_000).quantize(Decimal('1'), rounding=ROUND_HALF_UP)))
        return {'mode': request.mode, 'duration_seconds': micros / 1_000_000, 'price_cents': cents, 'currency': 'BRL'}

    @app.post('/api/courts/{court}/preview')
    def preview(court: str, request: TimeRange):
        segments = catalog(court)
        ranges = validate(segments, [request])
        if ranges[0][1] - ranges[0][0] > timedelta(seconds=60):
            raise HTTPException(422, 'Preview is limited to 60 seconds in this prototype.')
        if not preview_lock.acquire(blocking=False):
            raise HTTPException(429, 'Another preview is being generated.')
        try:
            previews.mkdir(parents=True, exist_ok=True)
            identifier = uuid4()
            with TemporaryDirectory(prefix='api-preview-', dir=previews) as temp:
                raw = export_ranges(segments, ranges, Path(temp) / 'raw.mp4')
                generate_preview(raw, previews / f'{identifier}.mp4')
            return {'id': str(identifier), 'url': f'/api/previews/{identifier}', 'watermarked': True}
        except (ValueError, RuntimeError, OSError):
            log.exception('Preview generation failed')
            raise HTTPException(503, 'Could not generate preview') from None
        finally:
            preview_lock.release()

    @app.get('/api/previews/{identifier}')
    def get_preview(identifier: UUID):
        path = previews / f'{identifier}.mp4'
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, 'Preview not found')
        return FileResponse(path, media_type='video/mp4', headers={'Cache-Control': 'no-store'})

    return app


app = create_app()
