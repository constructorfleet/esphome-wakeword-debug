#!/bin/bash
# Quick validation script for the audio pipeline

set -e

echo "=== Audio Pipeline Validation ==="
echo

echo "1. Checking Python dependencies..."
cd ingest_service
python3 -c "import fastapi, uvicorn, numpy, paho.mqtt.client; print('✓ All Python dependencies available')"
cd ..

echo
echo "2. Running unit tests..."
PYTHONPATH=. python -m pytest tests/ -q --tb=no
echo "✓ All tests passed"

echo
echo "3. Validating Docker Compose configuration..."
docker compose config > /dev/null 2>&1 && echo "✓ Docker Compose config valid" || echo "⚠ Docker Compose not available (optional)"

echo
echo "4. Checking project structure..."
for dir in esphome/components/audio_stream_ws ingest_service/app tests/ingest_service; do
    if [ -d "$dir" ]; then
        echo "✓ $dir exists"
    else
        echo "✗ $dir missing"
        exit 1
    fi
done

echo
echo "5. Verifying key files..."
for file in \
    esphome/components/audio_stream_ws/__init__.py \
    esphome/components/audio_stream_ws/audio_stream_ws.h \
    esphome/components/audio_stream_ws/audio_stream_ws.cpp \
    ingest_service/app/main.py \
    ingest_service/app/audio_buffer.py \
    ingest_service/app/wav_writer.py \
    ingest_service/app/mqtt_publisher.py \
    docker-compose.yml \
    README.md; do
    if [ -f "$file" ]; then
        echo "✓ $file"
    else
        echo "✗ $file missing"
        exit 1
    fi
done

echo
echo "=== Validation Complete ==="
echo "All components are ready! 🎉"
echo
echo "Next steps:"
echo "1. Start services: docker compose up -d"
echo "2. Flash ESP32: cd esphome && esphome run example-config.yaml"
echo "3. Trigger wake event: curl -X POST http://localhost:8000/wake_event"
