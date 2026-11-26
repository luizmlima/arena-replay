from datetime import UTC, datetime, timedelta
import subprocess

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from recorder.catalog import Segment
from video_worker import probe_video

BASE = datetime(2026, 11, 26, 2, 59, 55, tzinfo=UTC)


def rng(a, b):
    return {'start': (BASE + timedelta(seconds=a)).isoformat(), 'end': (BASE + timedelta(seconds=b)).isoformat()}


@pytest.fixture
def client(tmp_path, monkeypatch):
    def catalog(root, court):
        if court == 'court01':
            return [Segment(tmp_path / 'a.ts', BASE, BASE + timedelta(hours=2))]
        return []
    monkeypatch.setattr('backend.main.load_catalog', catalog)
    return TestClient(create_app(tmp_path))


def test_courts_and_health(client):
    assert client.get('/api/health').json() == {'status': 'ok'}
    assert [c['id'] for c in client.get('/api/courts').json()] == ['court01', 'court02', 'court03', 'court04']


def test_recordings_midnight(client):
    response = client.get('/api/courts/court01/recordings?day=2026-11-26')
    assert response.status_code == 200
    assert response.json()['segments'][0]['start'] == '2026-11-26T00:00:00-03:00'
    assert client.get('/api/courts/court09/recordings').status_code == 404
    assert client.get('/api/courts/court02/recordings').json()['segments'] == []


@pytest.mark.parametrize('ranges,cents', [([rng(0, 30)], 500), ([rng(0, 60), rng(65, 95)], 750), ([rng(0, 61)], 508)])
def test_replay_price(client, ranges, cents):
    response = client.post('/api/courts/court01/quote', json={'ranges': ranges})
    assert response.status_code == 200
    assert response.json()['price_cents'] == cents


def test_full_hour(client):
    result = client.post('/api/courts/court01/quote', json={'mode': 'full_hour', 'ranges': [rng(5, 3605)]})
    assert result.json()['price_cents'] == 5000
    assert client.post('/api/courts/court01/quote', json={'mode': 'full_hour', 'ranges': [rng(0, 3600)]}).status_code == 422


@pytest.mark.parametrize('ranges', [[rng(0, 30), rng(29, 40)], [rng(-1, 2)], [rng(4, 2)], [{'start': '2026-11-26T00:00:00', 'end': '2026-11-26T00:00:10'}]])
def test_bad_ranges(client, ranges):
    assert client.post('/api/courts/court01/quote', json={'ranges': ranges}).status_code == 422


def test_preview_limits(client):
    assert client.post('/api/courts/court01/preview', json=rng(0, 61)).status_code == 422
    assert client.get('/api/previews/00000000-0000-0000-0000-000000000000').status_code == 404
    assert client.get('/storage/recordings/a.ts').status_code == 404


def test_real_preview(tmp_path):
    root = tmp_path / 'recordings' / 'court01' / '2026-11-25' / '20261126T025955.000000Z-12345678'
    root.mkdir(parents=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=640x480:rate=30', '-t', '3', '-c:v', 'libx264', '-preset', 'ultrafast', '-g', '30', '-f', 'mpegts', str(root / '000000.ts')], check=True)
    (root / 'segments.csv').write_text('000000.ts,0,3\n')
    client = TestClient(create_app(tmp_path))
    result = client.post('/api/courts/court01/preview', json=rng(0, 2))
    assert result.status_code == 200, result.text
    response = client.get(result.json()['url'])
    assert response.status_code == 200 and response.headers['content-type'] == 'video/mp4'
    path = tmp_path / 'previews' / 'api' / (result.json()['id'] + '.mp4')
    assert probe_video(path).duration == pytest.approx(2, abs=0.12)
    assert probe_video(path).height <= 480
    assert list(path.parent.iterdir()) == [path]
