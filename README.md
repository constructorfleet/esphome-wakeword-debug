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
- **Multi-assistant support**: Publish to topics with assistant ID suffix (e.g., `satellite1/audio_debug/pcm/assistant1`)

### Ingest Service
- MQTT subscriber for base64-encoded audio chunks from ESPHome
- **Multi-assistant audio buffering**: Separate audio buffers for each assistant ID
- **Per-assistant audio configuration**: Dynamic audio parameters via MQTT retained messages
- Real-time audio buffering (configurable duration)
- Automatic wake event clip extraction on wake word detection
- Wake event clip extraction (pre/post event audio)
- WAV file generation with metadata
- MQTT event publishing
- Home Assistant auto-discovery
- REST API for manual triggers and monitoring
- Automatic cleanup of old audio files
- Legacy WebSocket support for backward compatibility

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

Edit `esphome/example-config.yaml` with your specific settings:

```yaml
# Update with your WiFi credentials
wifi:
  ssid: "YOUR_WIFI_SSID"
  password: "YOUR_WIFI_PASSWORD"

# Update with your MQTT broker details (IP address or hostname)
mqtt:
  broker: "YOUR_MQTT_BROKER"  # e.g., "192.168.1.100" or "mqtt.local"
  port: 1883
  username: "YOUR_MQTT_USERNAME"
  password: "YOUR_MQTT_PASSWORD"

# Update API and OTA keys
api:
  encryption:
    key: "YOUR_API_ENCRYPTION_KEY"

ota:
  password: "YOUR_OTA_PASSWORD"

# Update microphone I2S pins for your wiring
microphone:
  - platform: i2s_audio
    id: sat1_mics
    i2s_din_pin: GPIO26      # Data pin (SD on INMP441)
    i2s_bclk_pin: GPIO33     # Bit clock (SCK on INMP441)
    i2s_lrclk_pin: GPIO25    # Left/Right clock (WS on INMP441)
    adc_type: external
    pdm: false
    channel: left
    sample_rate: 48000       # Must match SAMPLE_RATE in .env
    bits_per_sample: 32bit   # Must match SAMPLE_WIDTH (4 bytes = 32 bits)
    on_data:
      then:
        - if:
            condition:
              - switch.is_on: enable_audio_debug
            then:
              - mqtt.publish:
                  topic: assist/audio_debug/${name}/pcm
                  payload: !lambda |-
                    return esphome::base64_encode(x);

on_boot:
  - then:
      mqtt.publish: 
        topic: assist/debug/${name}/audio_info
        retain: true
        payload: !lambda |-
          auto stream_info = id(sat1_mics).get_audio_stream_info();
          auto channels = std::to_string(stream_info.get_channels());
          auto sample_rate = std::to_string(stream_info.get_sample_rate());
          auto bits_per_sample = std::to_string(stream_info.get_bits_per_sample());

          return "{\"event\":\"wake\",\"rate\":" + sample_rate + ",\"bits\":" + bits_per_sample + ",\"channels\":" + channels + "}";

# Configure wake word models (update URLs to your model files)
micro_wake_word:
  id: mww
  microphone: sat1_mics
  models:
    - model: https://your-server.com/path/to/hey_eddie/hey_eddie.json
      id: hey_eddie
    - model: https://your-server.com/path/to/hey_eddie/hey_eddie.v3.0.json
      id: hey_eddie_v3_0
  on_wake_word_detected:
    - if:
        condition:
          - switch.is_on: enable_audio_debug
        then:
          - mqtt.publish:
              topic: assist/debug/${name}/events
              payload: !lambda |-
                auto stream_info = id(sat1_mics).get_audio_stream_info();
                auto channels = std::to_string(stream_info.get_channels());
                auto sample_rate = std::to_string(stream_info.get_sample_rate());
                auto bits_per_sample = std::to_string(stream_info.get_bits_per_sample());

                return "{\"event\":\"wake\",\"rate\":" + sample_rate + ",\"bits\":" + bits_per_sample + ",\"channels\":" + channels + "}";

# Debug audio switch (enables audio streaming to MQTT)
switch:
  - platform: template
    id: enable_audio_debug
    name: "Satellite1 Debug Audio"
    optimistic: true
    restore_mode: RESTORE_DEFAULT_OFF
```

### 3. Flash ESP32 Device

```bash
cd esphome
esphome run example-config.yaml
```

### 4. Trigger Wake Events

Use the REST API to capture audio clips:

```bash
# Trigger a wake event (captures 2s pre + 3s post) for default assistant
curl -X POST http://localhost:8000/wake_event

# Trigger for specific assistant
curl -X POST "http://localhost:8000/wake_event?assistant_id=assistant1"

# Custom duration
curl -X POST "http://localhost:8000/wake_event?pre_duration=3.0&post_duration=5.0"

# Check service health
curl http://localhost:8000/health

# View active assistants
curl http://localhost:8000/
```

Audio clips are saved to `./audio_clips/` directory.

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
# Audio settings (must match ESPHome configuration)
SAMPLE_RATE=48000          # Sample rate in Hz (48kHz to match example-config.yaml)
SAMPLE_WIDTH=4             # Bytes per sample (4=32bit to match example-config.yaml)
CHANNELS=1                 # Number of audio channels

# Buffer settings
BUFFER_DURATION_SECONDS=60.0      # Total buffer size
PRE_WAKE_DURATION_SECONDS=2.0     # Audio before wake event
POST_WAKE_DURATION_SECONDS=3.0    # Audio after wake event

# MQTT settings
MQTT_BROKER=mqtt           # MQTT broker hostname
MQTT_PORT=1883            # MQTT broker port
MQTT_TOPIC_PREFIX=wakeword/debug
MQTT_AUDIO_TOPIC=satellite1/audio_debug/pcm   # Topic for base64 audio data from ESPHome (wildcard + will be added)
MQTT_EVENT_TOPIC=satellite1/audio_debug/meta   # Topic for wake word events from ESPHome (wildcard + will be added)
MQTT_AUDIO_INFO_TOPIC=satellite1/audio_debug/audio_info  # Topic for audio info from ESPHome (wildcard + will be added)
```

**Important:** The MQTT topics (`MQTT_AUDIO_TOPIC`, `MQTT_AUDIO_INFO_TOPIC` and `MQTT_EVENT_TOPIC`) in the `.env` file can the full topic or the base topic paths **without** the assistant ID. The service will automatically subscribe to these topics with a wildcard (`+`) to support multiple assistants if necessary. For example:
- **Base topics** in `.env`: `satellite1/audio_debug/pcm` and `satellite1/audio_debug/meta`
- **Actual subscriptions**: `satellite1/audio_debug/pcm/+` and `satellite1/audio_debug/meta/+`
- **Device publishes to**: `satellite1/audio_debug/pcm/assistant1` and `satellite1/audio_debug/meta/assistant1`

Each assistant ID gets its own separate audio buffer, so multiple assistants can be running simultaneously without audio mixing.

### I2S Microphone Wiring

Example wiring for INMP441 (as shown in example-config.yaml):

| INMP441 Pin | ESP32 Pin  | Config Parameter | Description      |
|-------------|------------|------------------|------------------|
| VDD         | 3.3V       | -                | Power            |
| GND         | GND        | -                | Ground           |
| SD          | GPIO 26    | i2s_din_pin      | Data In          |
| WS          | GPIO 25    | i2s_lrclk_pin    | Word Select/LR   |
| SCK         | GPIO 33    | i2s_bclk_pin     | Bit Clock        |

**Note:** These are the default pins used in `example-config.yaml`. Adjust them in your configuration if your wiring is different.

## API Endpoints

**Note:** The ingest service supports both WebSocket audio streaming (legacy) and MQTT-based streaming with multi-assistant support.

### WebSocket (Legacy)
- `ws://host:8000/ws/audio` - Audio streaming endpoint (single stream, no assistant separation)

### REST API
- `GET /` - Service information (includes list of active assistants)
- `GET /health` - Health check (includes active assistant count)
- `POST /wake_event` - Trigger wake event and save clip
  - Query params: `assistant_id` (default: "default"), `pre_duration`, `post_duration`
- `POST /clear_buffer` - Clear audio buffer
  - Query params: `assistant_id` (optional - clears specific assistant or all if omitted)
- `POST /cleanup` - Cleanup old WAV files
  - Query params: `max_age_days`

### Multi-Assistant Support

The service automatically manages separate audio buffers for each assistant ID. When devices publish to topics like:
- `satellite1/audio_debug/assistant1/pcm`
- `satellite1/audio_debug/assistant1/events`
- `satellite1/audio_debug/assistant1/audio_info` (retained)

The service will:
1. Extract the assistant ID (`assistant1`) from the topic
2. Create and maintain a separate audio buffer for that assistant
3. Route wake events to the correct assistant's buffer
4. Include the assistant ID in saved clip metadata

#### Per-Assistant Audio Configuration

Each assistant can publish a retained message to `satellite1/audio_debug/{assistant_id}/audio_info` containing its audio configuration:

```json
{
  "sample_rate": 48000,
  "bits_per_sample": 32,
  "channels": 1
}
```

This allows the service to:
- Configure buffers with the correct audio parameters for each assistant
- Support different audio formats simultaneously (e.g., one assistant at 16kHz/16-bit, another at 48kHz/32-bit)
- Automatically create properly configured buffers when audio data arrives
- Fall back to global defaults if no configuration is provided

**Example ESPHome configuration:**
```yaml
on_boot:
  - priority: -100
    then:
      - mqtt.publish:
          topic: satellite1/audio_debug/assistant1/audio_info
          payload: '{"sample_rate":48000,"bits_per_sample":32,"channels":1}'
          retain: true
```

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
