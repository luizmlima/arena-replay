#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/../.."

SOURCE="storage/recordings/test.mp4"
PIDS=()

if [[ ! -f "$SOURCE" ]]; then
    echo "Test video not found: $SOURCE"
    exit 1
fi

cleanup() {
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait || true
}

trap cleanup EXIT
trap 'exit 0' INT TERM

for court in 01 02 03 04; do
    URL="rtsp://127.0.0.1:8554/court${court}"

    ffmpeg -hide_banner -loglevel error \
        -re -stream_loop -1 \
        -i "$SOURCE" \
        -an -c:v copy \
        -f rtsp -rtsp_transport tcp \
        "$URL" &

    PIDS+=("$!")
    echo "Starting camera: $URL"
done

echo "Press Ctrl+C to stop all cameras."

wait -n
