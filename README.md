# ESPHome Wake Word Debug Pipeline

A comprehensive audio capture and processing pipeline for wake word debugging, consisting of:
- **ESPHome Configuration**: Captures I2S microphone audio and streams base64-encoded PCM chunks over MQTT
- **Python FastAPI Ingest Service**: Buffers audio, extracts clips around wake events, writes WAV files, and publishes MQTT events
- **Home Assistant Integration**: React to wake word events via MQTT

## Architecture

```
┌─────────────────┐           MQTT             ┌──────────────────┐
│  ESP32 Device   │ ───────(Base64 PCM)──────> │  MQTT Broker     │
│  + I2S Mic      │                             │  (Mosquitto)     │
│  + ESPHome      │                             │                  │
│  + Micro Wake   │                             └────────┬─────────┘
│    Word         │                                      │
└─────────────────┘                                      │ MQTT
                                                         ▼
                                                ┌──────────────────┐
                                                │ Ingest Service   │
                                                │  (FastAPI)       │
                                                │                  │
                                                │ • Audio Buffer   │
                                                │ • WAV Writer     │
                                                │ • MQTT Subscriber│
                                                └────────┬─────────┘
                                                         │ MQTT
                                                         ▼
                                                ┌──────────────────┐
                                                │ Home Assistant   │
                                                └──────────────────┘
```

## Features

### ESPHome Configuration
- I2S microphone capture (48kHz, 32-bit PCM)
- MQTT streaming of base64-encoded audio chunks
- Micro wake word detection with configurable models
- Conditional audio debug streaming via switch
- Wake word event metadata publishing

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

# Update with your MQTT broker details
mqtt:
  broker: "YOUR_MQTT_BROKER"
  port: 1883
  username: "YOUR_MQTT_USERNAME"
  password: "YOUR_MQTT_PASSWORD"

# Update microphone I2S pins for your wiring
microphone:
  - platform: i2s_audio
    i2s_din_pin: 26  # Adjust for your wiring
    # Additional configuration in the example file

# Configure wake word models
micro_wake_word:
  models:
    - model: https://your-server.com/path/to/model.json
      id: your_model
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

| INMP441 Pin | ESP32 Pin  | Config Parameter | Description      |
|-------------|------------|------------------|------------------|
| VDD         | 3.3V       | -                | Power            |
| GND         | GND        | -                | Ground           |
| SD          | GPIO 26    | i2s_din_pin      | Data In          |
| WS          | GPIO 25    | i2s_lrclk_pin    | Word Select/LR   |
| SCK         | GPIO 33    | i2s_bclk_pin     | Bit Clock        |

## API Endpoints

**Note:** The ingest service currently supports WebSocket audio streaming. With the new MQTT-based approach, the service can be extended to subscribe to MQTT topics for audio data instead of/in addition to WebSocket connections.

### WebSocket (Legacy)
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
- Check MQTT broker connectivity (use IP address if hostname doesn't resolve)
- Check firewall rules on server

### No Audio Data
- Verify I2S wiring (see wiring table above)
- Check I2S pin configuration in example-config.yaml
- Ensure the "Satellite1 Debug Audio" switch is turned on in Home Assistant
- View ESPHome logs: `esphome logs example-config.yaml`
- Monitor MQTT topics: `mosquitto_sub -h localhost -t "satellite1/audio_debug/#" -v`

### Wake Word Not Detecting
- Verify wake word model URLs are accessible
- Check micro_wake_word configuration
- View ESPHome logs for wake word detection events
- Ensure the "Satellite1 Debug Audio" switch is enabled

### MQTT Not Working
- Check MQTT broker is running: `docker-compose logs mqtt`
- Verify MQTT broker address in example-config.yaml
- Test MQTT connection: `mosquitto_sub -h localhost -t "satellite1/audio_debug/#" -v`
- Verify MQTT credentials if authentication is enabled

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request
