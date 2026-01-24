import base64
import json
import logging
from typing import Optional, Callable
import paho.mqtt.client as mqtt

from .config import settings

logger = logging.getLogger(__name__)


class MQTTSubscriber:
    """Handles MQTT subscription for audio data and wake word events."""
    
    def __init__(
        self,
        broker: str = settings.MQTT_BROKER,
        port: int = settings.MQTT_PORT,
        username: Optional[str] = settings.MQTT_USERNAME,
        password: Optional[str] = settings.MQTT_PASSWORD,
        client_id: str = f"{settings.MQTT_CLIENT_ID}-subscriber",
        audio_topic: str = settings.MQTT_AUDIO_TOPIC,
        meta_topic: str = settings.MQTT_META_TOPIC
    ):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id
        self.audio_topic = audio_topic
        self.meta_topic = meta_topic
        
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        
        # Callbacks for handling messages
        self.audio_callback: Optional[Callable[[bytes], None]] = None
        self.wake_callback: Optional[Callable[[dict], None]] = None
        
        logger.info(
            f"MQTTSubscriber initialized: broker={broker}:{port}, "
            f"audio_topic={audio_topic}, meta_topic={meta_topic}"
        )
    
    def set_audio_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set callback for handling audio data."""
        self.audio_callback = callback
    
    def set_wake_callback(self, callback: Callable[[dict], None]) -> None:
        """Set callback for handling wake word events."""
        self.wake_callback = callback
    
    def connect(self) -> bool:
        """
        Connect to MQTT broker and subscribe to topics.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client = mqtt.Client(client_id=self.client_id)
            
            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            # Set credentials if provided
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            # Connect to broker
            self.client.connect(self.broker, self.port, keepalive=60)
            
            # Start network loop in background
            self.client.loop_start()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("Disconnected from MQTT broker")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when client connects to broker."""
        if rc == 0:
            self.connected = True
            logger.info("MQTT Subscriber connected to broker")
            
            # Subscribe to topics
            client.subscribe(self.audio_topic, qos=0)
            client.subscribe(self.meta_topic, qos=1)
            logger.info(f"Subscribed to {self.audio_topic} and {self.meta_topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when client disconnects from broker."""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected MQTT disconnect: {rc}")
        else:
            logger.info("MQTT Subscriber disconnected from broker")
    
    def _on_message(self, client, userdata, msg):
        """Callback for when a message is received."""
        try:
            if msg.topic == self.audio_topic:
                # Handle audio data (base64 encoded)
                if self.audio_callback:
                    try:
                        # Decode base64 audio data
                        audio_data = base64.b64decode(msg.payload)
                        self.audio_callback(audio_data)
                    except Exception as e:
                        logger.error(f"Error decoding audio data: {e}")
                else:
                    logger.warning("Received audio data but no callback set")
            
            elif msg.topic == self.meta_topic:
                # Handle wake word metadata
                if self.wake_callback:
                    try:
                        # Parse JSON metadata
                        metadata = json.loads(msg.payload)
                        self.wake_callback(metadata)
                    except Exception as e:
                        logger.error(f"Error parsing wake metadata: {e}")
                else:
                    logger.warning("Received wake metadata but no callback set")
        
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
