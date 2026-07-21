import os
from typing import Optional

class Settings:
    """Application settings loaded from environment variables."""
    
    # Server settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Audio settings
    SAMPLE_RATE: int = int(os.getenv("SAMPLE_RATE", "48000"))  # Match ESPHome: 48kHz
    SAMPLE_WIDTH: int = int(os.getenv("SAMPLE_WIDTH", "4"))  # 4 bytes = 32 bits
    CHANNELS: int = int(os.getenv("CHANNELS", "1"))  # Mono
    
    # Buffer settings
    BUFFER_DURATION_SECONDS: float = float(os.getenv("BUFFER_DURATION_SECONDS", "60.0"))
    PRE_WAKE_DURATION_SECONDS: float = float(os.getenv("PRE_WAKE_DURATION_SECONDS", "2.0"))
    POST_WAKE_DURATION_SECONDS: float = float(os.getenv("POST_WAKE_DURATION_SECONDS", "3.0"))
    
    # Storage settings
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "/app/audio_clips")
    CLIP_DB_PATH: str = os.getenv("CLIP_DB_PATH", os.path.join(OUTPUT_DIR, "clips.db"))
    
    # UDP audio ingest settings
    # The satellite1 `wake_audio_stream` component streams raw PCM over UDP. It sends what
    # microWakeWord processes: int16 (2-byte) samples, mono, 16 kHz, little-endian, unframed.
    UDP_ENABLED: bool = os.getenv("UDP_ENABLED", "true").lower() in ("1", "true", "yes")
    UDP_HOST: str = os.getenv("UDP_HOST", "0.0.0.0")
    UDP_PORT: int = int(os.getenv("UDP_PORT", "6056"))
    UDP_SAMPLE_RATE: int = int(os.getenv("UDP_SAMPLE_RATE", "16000"))
    UDP_SAMPLE_WIDTH: int = int(os.getenv("UDP_SAMPLE_WIDTH", "2"))  # 2 bytes = 16 bits
    UDP_CHANNELS: int = int(os.getenv("UDP_CHANNELS", "1"))
    # If set, all UDP audio is attributed to this assistant ID. If empty, the sender's IP
    # address is used so multiple devices are tracked as separate assistants.
    UDP_ASSISTANT_ID: str = os.getenv("UDP_ASSISTANT_ID", "")

    # MQTT settings
    MQTT_BROKER: str = os.getenv("MQTT_BROKER", "localhost")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
    MQTT_USERNAME: Optional[str] = os.getenv("MQTT_USERNAME")
    MQTT_PASSWORD: Optional[str] = os.getenv("MQTT_PASSWORD")
    MQTT_TOPIC_PREFIX: str = os.getenv("MQTT_TOPIC_PREFIX", "wakeword/debug")
    MQTT_CLIENT_ID: str = os.getenv("MQTT_CLIENT_ID", "wakeword-ingest-service")
    MQTT_AUDIO_TOPIC: str = os.getenv("MQTT_AUDIO_TOPIC", "assist/debug/+/pcm")
    MQTT_EVENT_TOPIC: str = os.getenv("MQTT_EVENT_TOPIC", "assist/debug/+/events")
    MQTT_AUDIO_INFO_TOPIC: str = os.getenv("MQTT_AUDIO_INFO_TOPIC", "assist/debug/+/audio_info")
    
    # Home Assistant Discovery
    HASS_DISCOVERY_PREFIX: str = os.getenv("HASS_DISCOVERY_PREFIX", "homeassistant")

settings = Settings()
