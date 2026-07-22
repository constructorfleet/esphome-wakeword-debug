# ESPHome Wake Word Debug Pipeline

A comprehensive audio capture and processing pipeline for wake word debugging, consisting of:
- **ESPHome Configuration**: Captures wake-word audio and streams it to the ingest service. Two transports are supported:
  - **UDP** (recommended): the satellite1 `wake_audio_stream` component streams the exact PCM microWakeWord processes (int16 / mono / 16 kHz) as raw datagrams — low overhead, no broker required.
  - **MQTT**: base64-encoded PCM chunks published to a topic (legacy / broker-based setups).
- **Python FastAPI Ingest Service**: Buffers audio, extracts clips around wake events, writes WAV files, and publishes MQTT events
- **Home Assistant Integration**: React to wake word events via MQTT

## Architecture

```
                     UDP (raw int16 PCM audio)
┌─────────────────┐  + HTTP POST /wake_event   ┌──────────────────┐
│  satellite1     │ ─────────────────────────> │ Ingest Service   │
│  + wake_audio_  │       (no broker)           │  (FastAPI)       │
│    stream       │                             │                  │
│  + microWakeWord│   ──────── or ────────      │ • UDP Receiver   │
│                 │   MQTT (base64 PCM audio    │ • MQTT Subscriber│
│                 │        + wake events)       │ • Audio Buffer   │
└─────────────────┘ ──────────────────┐         │ • WAV Writer     │
                                       ▼         └────────┬─────────┘
                              ┌──────────────┐            │
                              │ MQTT Broker  │<───────────┘
                              │ (Mosquitto)  │   wake events (MQTT)
                              └──────┬───────┘            │
                                     └───────> Home Assistant
```

**Note:** Wake-word events can arrive two ways:
- **MQTT** (`assist/debug/+/events`) — used by the MQTT audio path.
- **HTTP** (`POST /wake_event`) — used by the UDP path, so a UDP-only device needs **no MQTT broker
  at all**. The satellite1 firmware posts to this endpoint from `on_wake_word_detected`. Direct
  connections may omit `assistant_id` and use the caller's IP; deployments behind Traefik or
  another proxy must send the same explicit assistant ID in the UDP packet and HTTP request.
  You can also hit the endpoint manually, or use the "capture background noise" button in the UI.

## Features

### ESPHome Configuration
- I2S microphone capture (48kHz, 32-bit PCM)
- MQTT streaming of base64-encoded audio chunks
- Micro wake word detection with configurable models
- Conditional audio debug streaming via switch
- Wake word event metadata publishing
- **Multi-assistant support**: Publish to topics with assistant ID in the middle (e.g., `assist/debug/assistant1/pcm` matches pattern `assist/debug/+/pcm`)

### Ingest Service
- **UDP receiver** for raw PCM audio from the satellite1 `wake_audio_stream` component (int16 / mono / 16 kHz)
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

#### Alternative: UDP audio from the satellite1 `wake_audio_stream` component

If you build the satellite1 firmware with the `wake_audio_stream` component (see the
`satellite1-esphome` repo), audio is streamed over UDP instead of MQTT. That component taps
microWakeWord's `on_audio_data` trigger, so it sends the exact audio the wake-word models
process (int16 / mono / 16 kHz) — including audio where no wake word fired, which is what you
want for false-negative training data.

On the satellite1 side, point the stream at this service and toggle capture with the
"Capture wake-word audio" switch:

```yaml
wake_audio_stream:
  id: wake_audio_streamer
  ip_address: 192.168.1.100   # host running this ingest service
  port: 6056                  # must match UDP_PORT
  buffer_duration: 500ms
```

The ingest service listens on `UDP_PORT` (default `6056`) with no further config. It accepts both:

- **Framed UDP packets (recommended):** `WWD1`, one byte containing the assistant-ID length,
  the ASCII assistant ID, and the raw PCM payload. This preserves identity through Traefik and
  other UDP proxies. IDs may contain letters, numbers, `_`, `.`, and `-`, must begin with a letter
  or number, and are limited to 64 bytes. The current satellite1 `wake_audio_stream` component
  automatically uses the ESPHome node name.
- **Legacy raw PCM packets:** the sender IP is used as the assistant ID. This is suitable only when
  devices connect directly and have distinct visible IP addresses.

`UDP_ASSISTANT_ID` remains a fixed override for single-assistant deployments and deliberately sends
all received audio to one buffer.

The satellite1 firmware also posts to `POST /wake_event` from `on_wake_word_detected` (gated on the
same capture switch), so **no MQTT broker is needed** for the UDP path. When traffic passes through
Traefik, include the ID from the framed UDP packet explicitly so the event selects the right buffer:

```yaml
micro_wake_word:
  on_wake_word_detected:
    - if:
        condition:
          switch.is_on: wake_audio_capture
        then:
          - http_request.post:
              url: !lambda 'return "https://wake-debug.example/wake_event?assistant_id=kitchen&wake_word=" + wake_word;'
              capture_response: false
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

# UDP audio ingest (satellite1 wake_audio_stream component)
UDP_ENABLED=true          # Listen for raw PCM over UDP
UDP_HOST=0.0.0.0          # Bind address
UDP_PORT=6056             # Must match the component's `port:`
UDP_SAMPLE_RATE=16000     # microWakeWord audio: 16 kHz
UDP_SAMPLE_WIDTH=2        # 2 bytes (16-bit)
UDP_CHANNELS=1            # Mono
UDP_ASSISTANT_ID=         # Fixed override; empty = framed packet ID or sender IP

# Buffer settings
BUFFER_DURATION_SECONDS=60.0      # Total buffer size
PRE_WAKE_DURATION_SECONDS=2.0     # Audio before wake event
POST_WAKE_DURATION_SECONDS=3.0    # Audio after wake event

# MQTT settings
MQTT_BROKER=mqtt           # MQTT broker hostname
MQTT_PORT=1883            # MQTT broker port
MQTT_TOPIC_PREFIX=wakeword/debug
MQTT_AUDIO_TOPIC=assist/debug/+/pcm   # Pattern for audio data with wildcard
MQTT_EVENT_TOPIC=assist/debug/+/events  # Pattern for wake word events with wildcard
MQTT_AUDIO_INFO_TOPIC=assist/debug/+/audio_info  # Pattern for audio configuration with wildcard
```

**Important:** The MQTT topics use wildcard patterns with `+` to match any assistant ID:
- **Topic patterns** in `.env`: `assist/debug/+/pcm`, `assist/debug/+/events`, `assist/debug/+/audio_info`
- **Service subscribes to**: These exact wildcard patterns
- **Device publishes to**: `assist/debug/assistant1/pcm`, `assist/debug/assistant1/events`, `assist/debug/assistant1/audio_info`

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
- `assist/debug/assistant1/pcm`
- `assist/debug/assistant1/events`
- `assist/debug/assistant1/audio_info` (retained)

The service will:
1. Extract the assistant ID (`assistant1`) from the topic using the wildcard pattern
2. Create and maintain a separate audio buffer for that assistant
3. Route wake events to the correct assistant's buffer
4. Include the assistant ID in saved clip metadata

#### Per-Assistant Audio Configuration

Each assistant can publish a retained message to `assist/debug/{assistant_id}/audio_info` containing its audio configuration:

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
          topic: assist/debug/assistant1/audio_info
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
- Monitor MQTT topics: `mosquitto_sub -h localhost -t "assist/debug/#" -v`

### Wake Word Not Detecting
- Verify wake word model URLs are accessible
- Check micro_wake_word configuration
- View ESPHome logs for wake word detection events
- Ensure the "Satellite1 Debug Audio" switch is enabled

### MQTT Not Working
- Check MQTT broker is running: `docker-compose logs mqtt`
- Verify MQTT broker address in example-config.yaml
- Test MQTT connection: `mosquitto_sub -h localhost -t "assist/debug/#" -v`
- Verify MQTT credentials if authentication is enabled

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request
