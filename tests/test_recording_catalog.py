from datetime import UTC, datetime, timedelta
import shutil
import subprocess

import pytest

from recorder.catalog import CatalogError, export_ranges, load_catalog, select_range
from recorder.continuous import ffmpeg_command
from video_worker import probe_video

BASE = datetime(2026, 11, 26, 2, 59, 55, tzinfo=UTC)


def at(seconds):
    return BASE + timedelta(seconds=seconds)


def session(root):
    path = root / 'court01' / '2026-11-25' / '20261126T025955.000000Z-12345678'
    path.mkdir(parents=True)
    return path


def fixture(root, rows, monkeypatch):
    timing = {name: (1.4, b - a) for name, a, b in rows}
    monkeypatch.setattr("recorder.catalog._video_timing", lambda path: timing[path.name])
    path = session(root)
    (path / 'segments.csv').write_text(''.join(f'{name},{a},{b}\n' for name, a, b in rows))
    for name, _, _ in rows:
        (path / name).write_bytes(b'test')
    return path


def test_cross_midnight_and_segment_boundary(tmp_path, monkeypatch):
    fixture(tmp_path, [('000000.ts', 0, 10), ('000001.ts', 10, 20)], monkeypatch)
    segments = load_catalog(tmp_path, 'court01')
    assert len(segments) == 2
    pieces = select_range(segments, at(3), at(14))
    assert [(p.start, p.end) for p in pieces] == [(3, 10), (0, 4)]
    assert segments[1].start == at(10)
    assert not load_catalog(tmp_path, 'court02')


def test_exact_boundary(tmp_path, monkeypatch):
    fixture(tmp_path, [('000000.ts', 0, 10), ('000001.ts', 10, 20)], monkeypatch)
    pieces = select_range(load_catalog(tmp_path, 'court01'), at(10), at(20))
    assert len(pieces) == 1 and pieces[0].start == 0


def test_gap(tmp_path, monkeypatch):
    fixture(tmp_path, [('000000.ts', 0, 10), ('000001.ts', 12, 20)], monkeypatch)
    with pytest.raises(CatalogError, match='gap'):
        select_range(load_catalog(tmp_path, 'court01'), at(5), at(15))


def test_overlap(tmp_path, monkeypatch):
    fixture(tmp_path, [('000000.ts', 0, 10), ('000001.ts', 9, 20)], monkeypatch)
    with pytest.raises(CatalogError, match='overlapping'):
        select_range(load_catalog(tmp_path, 'court01'), at(5), at(15))


def test_missing_file(tmp_path, monkeypatch):
    path = fixture(tmp_path, [('000000.ts', 0, 10), ('000001.ts', 10, 20)], monkeypatch)
    (path / '000001.ts').unlink()
    with pytest.raises(CatalogError, match='gap'):
        select_range(load_catalog(tmp_path, 'court01'), at(5), at(15))


def test_invalid_manifest(tmp_path):
    path = session(tmp_path)
    (path / 'segments.csv').write_text('../outside.ts,0,10\n')
    with pytest.raises(CatalogError, match='filename'):
        load_catalog(tmp_path, 'court01')


def test_naive_datetime():
    with pytest.raises(CatalogError, match='offset'):
        select_range([], datetime(2026, 11, 25), at(1))


def test_selection_overlap(tmp_path, monkeypatch):
    fixture(tmp_path, [('000000.ts', 0, 10)], monkeypatch)
    with pytest.raises(CatalogError, match='overlap'):
        export_ranges(load_catalog(tmp_path, 'court01'), [(at(0), at(5)), (at(4), at(6))], tmp_path / 'out.mp4')


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_real_segment_export(tmp_path):
    source = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=30', '-t', '6', '-c:v', 'libx264', '-preset', 'ultrafast', '-g', '30', '-keyint_min', '30', '-sc_threshold', '0', str(source)], check=True)
    path = session(tmp_path)
    command = ffmpeg_command('rtsp://localhost/court01', path, 2)
    command[command.index('-rtsp_transport'):command.index('-map')] = ['-i', str(source)]
    subprocess.run(command, check=True)
    segments = load_catalog(tmp_path, 'court01')
    assert len(segments) == 3
    # Deliberately reversed ranges; one crosses a segment boundary.
    output = export_ranges(segments, [(at(4), at(5)), (at(1), at(3))], tmp_path / 'out.mp4')
    assert probe_video(output).duration == pytest.approx(3, abs=0.12)
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(output), '-f', 'null', '-'], check=True)


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_rtsp_startup_timestamp_offset(tmp_path):
    source = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=30', '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-g', '30', '-sc_threshold', '0', str(source)], check=True)
    path = session(tmp_path)
    for name, offset in [('000000.ts', '0.633333'), ('000001.ts', '0')]:
        subprocess.run(['ffmpeg', '-v', 'error', '-itsoffset', offset, '-i', str(source), '-map', '0:v:0', '-c', 'copy', '-f', 'mpegts', str(path / name)], check=True)
    manifest = path / 'segments.csv'
    original = '000000.ts,0,2.633333\n000001.ts,2.633333,4.633333\n'
    manifest.write_text(original)
    segments = load_catalog(tmp_path, 'court01')
    assert segments[0].start == at(0.633333)
    assert segments[0].end == segments[1].start == at(2.633333)
    with pytest.raises(CatalogError, match='gap'):
        select_range(segments, at(0), at(1))
    result = export_ranges(segments, [(at(1), at(4))], tmp_path / 'out.mp4')
    assert probe_video(result).duration == pytest.approx(3, abs=0.12)
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(result), '-f', 'null', '-'], check=True)
    assert manifest.read_text() == original


def test_unverified_startup_discrepancy(tmp_path, monkeypatch):
    fixture(tmp_path, [('000000.ts', 0, 10.633333), ('000001.ts', 10.633333, 20.633333)], monkeypatch)
    monkeypatch.setattr('recorder.catalog._video_timing', lambda path: (1.4, 10.0))
    with pytest.raises(CatalogError, match='Unverified startup timestamp discrepancy'):
        load_catalog(tmp_path, 'court01')
