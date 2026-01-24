import os
from typing import Optional

class Settings:
    """Application settings loaded from environment variables."""
    
    # Server settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Audio settings
    SAMPLE_RATE: int = int(os.getenv("SAMPLE_RATE", "16000"))
    SAMPLE_WIDTH: int = int(os.getenv("SAMPLE_WIDTH", "2"))  # 2 bytes = 16 bits
    CHANNELS: int = int(os.getenv("CHANNELS", "1"))  # Mono
    
    # Buffer settings
    BUFFER_DURATION_SECONDS: float = float(os.getenv("BUFFER_DURATION_SECONDS", "60.0"))
    PRE_WAKE_DURATION_SECONDS: float = float(os.getenv("PRE_WAKE_DURATION_SECONDS", "2.0"))
    POST_WAKE_DURATION_SECONDS: float = float(os.getenv("POST_WAKE_DURATION_SECONDS", "3.0"))
    
    # Storage settings
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "/app/audio_clips")
    
    # MQTT settings
    MQTT_BROKER: str = os.getenv("MQTT_BROKER", "localhost")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
    MQTT_USERNAME: Optional[str] = os.getenv("MQTT_USERNAME")
    MQTT_PASSWORD: Optional[str] = os.getenv("MQTT_PASSWORD")
    MQTT_TOPIC_PREFIX: str = os.getenv("MQTT_TOPIC_PREFIX", "wakeword/debug")
    MQTT_CLIENT_ID: str = os.getenv("MQTT_CLIENT_ID", "wakeword-ingest-service")
    
    # Home Assistant Discovery
    HASS_DISCOVERY_PREFIX: str = os.getenv("HASS_DISCOVERY_PREFIX", "homeassistant")

settings = Settings()
