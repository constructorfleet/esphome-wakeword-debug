# ESPHome Wake Word Debug Pipeline

A comprehensive audio capture and processing pipeline for wake word debugging, consisting of:
- **ESPHome Component**: Captures I2S microphone audio and streams raw PCM over WebSocket
- **Python FastAPI Ingest Service**: Buffers audio, extracts clips around wake events, writes WAV files, and publishes MQTT events
- **Home Assistant Integration**: React to wake word events via MQTT

## Architecture

```
┌─────────────────┐         WebSocket          ┌──────────────────┐
│  ESP32 Device   │ ─────────(PCM Audio)─────> │ Ingest Service   │
│  + I2S Mic      │                             │  (FastAPI)       │
│  + ESPHome      │                             │                  │
└─────────────────┘                             │ • Audio Buffer   │
                                                │ • WAV Writer     │
                                                │ • MQTT Publisher │
                                                └────────┬─────────┘
                                                         │ MQTT
                                                         ▼
                                                ┌──────────────────┐
                                                │  MQTT Broker     │
                                                │  (Mosquitto)     │
                                                └────────┬─────────┘
                                                         │
                                                         ▼
                                                ┌──────────────────┐
                                                │ Home Assistant   │
                                                └──────────────────┘
```

## Features

### ESPHome Component
- I2S microphone capture (16kHz, 16-bit PCM)
- WebSocket streaming of raw audio data
- Configurable sample rate and bit depth
- Auto-reconnect on connection loss
- Start/stop actions via Home Assistant

### Ingest Service
- Real-time audio buffering (configurable duration)
- Wake event clip extraction (pre/post event audio)
- WAV file generation with metadata
- MQTT event publishing
- Home Assistant auto-discovery
- REST API for manual triggers and monitoring
- Automatic cleanup of old audio files

## Quick Start

### Prerequisites
- ESP32 development board
- I2S MEMS microphone (e.g., INMP441, SPH0645)
- Docker and Docker Compose
- ESPHome CLI (for ESP32 firmware)

### 1. Start the Services

```bash
# Clone the repository
git clone https://github.com/constructorfleet/esphome-wakeword-debug.git
cd esphome-wakeword-debug

# Start MQTT broker and ingest service
docker-compose up -d

# Check service status
docker-compose ps
curl http://localhost:8000/health
```

### 2. Configure ESPHome Device

Edit `esphome/example-config.yaml`:

```yaml
# Update with your WiFi credentials
wifi:
  ssid: "YOUR_WIFI_SSID"
  password: "YOUR_WIFI_PASSWORD"

# Update with your ingest service IP
audio_stream_ws:
  url: "ws://YOUR_SERVER_IP:8000/ws/audio"
  i2s_din_pin: 26  # Adjust for your wiring
  i2s_ws_pin: 25
  i2s_clk_pin: 33
```

### 3. Flash ESP32 Device

```bash
cd esphome
esphome run example-config.yaml
```

### 4. Trigger Wake Events

Use the REST API to capture audio clips:

```bash
# Trigger a wake event (captures 2s pre + 3s post)
curl -X POST http://localhost:8000/wake_event

# Custom duration
curl -X POST "http://localhost:8000/wake_event?pre_duration=3.0&post_duration=5.0"

# Check service health
curl http://localhost:8000/health
```

Audio clips are saved to `./audio_clips/` directory.

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
# Audio settings
SAMPLE_RATE=16000          # Sample rate in Hz
SAMPLE_WIDTH=2             # Bytes per sample (2=16bit, 4=32bit)
CHANNELS=1                 # Number of audio channels

# Buffer settings
BUFFER_DURATION_SECONDS=60.0      # Total buffer size
PRE_WAKE_DURATION_SECONDS=2.0     # Audio before wake event
POST_WAKE_DURATION_SECONDS=3.0    # Audio after wake event

# MQTT settings
MQTT_BROKER=mqtt           # MQTT broker hostname
MQTT_PORT=1883            # MQTT broker port
MQTT_TOPIC_PREFIX=wakeword/debug
```

### I2S Microphone Wiring

Example wiring for INMP441:

| INMP441 Pin | ESP32 Pin  | Description      |
|-------------|------------|------------------|
| VDD         | 3.3V       | Power            |
| GND         | GND        | Ground           |
| SD          | GPIO 26    | Data In (DIN)    |
| WS          | GPIO 25    | Word Select      |
| SCK         | GPIO 33    | Clock            |

## API Endpoints

### WebSocket
- `ws://host:8000/ws/audio` - Audio streaming endpoint

### REST API
- `GET /` - Service information
- `GET /health` - Health check
- `POST /wake_event` - Trigger wake event and save clip
  - Query params: `pre_duration`, `post_duration`
- `POST /clear_buffer` - Clear audio buffer
- `POST /cleanup` - Cleanup old WAV files
  - Query params: `max_age_days`

## Home Assistant Integration

The service automatically publishes MQTT discovery messages. After starting:

1. Open Home Assistant
2. Go to Settings → Devices & Services
3. Look for "Wake Word Debugger" device
4. You'll see a binary sensor that triggers on wake events

### Example Automation

```yaml
automation:
  - alias: "Log Wake Word Events"
    trigger:
      - platform: mqtt
        topic: "wakeword/debug/event"
    action:
      - service: notify.notify
        data:
          message: "Wake word detected! Audio saved to {{ trigger.payload_json.wav_file }}"
```

## Development

### Running Tests

```bash
# Install dependencies
cd ingest_service
pip install -r requirements.txt

# Run tests
cd ..
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=ingest_service --cov-report=html
```

### Project Structure

```
esphome-wakeword-debug/
├── esphome/
│   ├── components/
│   │   └── audio_stream_ws/      # ESPHome component
│   │       ├── __init__.py
│   │       ├── audio_stream_ws.h
│   │       └── audio_stream_ws.cpp
│   └── example-config.yaml        # Example ESPHome config
├── ingest_service/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI application
│   │   ├── config.py             # Configuration
│   │   ├── audio_buffer.py       # Audio buffering
│   │   ├── wav_writer.py         # WAV file generation
│   │   └── mqtt_publisher.py     # MQTT integration
│   ├── requirements.txt
│   └── Dockerfile
├── tests/
│   └── ingest_service/           # Unit tests
├── mosquitto/
│   └── config/                   # MQTT broker config
├── docker-compose.yml
└── README.md
```

## Troubleshooting

### ESP32 Not Connecting
- Verify WiFi credentials
- Check WebSocket URL (use IP address, not hostname)
- Check firewall rules on server

### No Audio Data
- Verify I2S wiring
- Check I2S pin configuration
- View ESPHome logs: `esphome logs example-config.yaml`

### MQTT Not Working
- Check MQTT broker is running: `docker-compose logs mqtt`
- Verify MQTT_BROKER environment variable
- Test with MQTT client: `mosquitto_sub -h localhost -t "wakeword/debug/#" -v`

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request
