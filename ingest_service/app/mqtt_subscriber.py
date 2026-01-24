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
        # Support wildcard topics for multiple assistants
        self.audio_topic = audio_topic if audio_topic.endswith('/+') else f"{audio_topic}/+"
        self.meta_topic = meta_topic if meta_topic.endswith('/+') else f"{meta_topic}/+"
        # Audio info topic for per-assistant audio configuration
        self.audio_info_topic = f"{meta_topic.rstrip('/+')}/+/audio_info"
        # Store base topics for pattern matching
        self.audio_topic_base = audio_topic.rstrip('/+')
        self.meta_topic_base = meta_topic.rstrip('/+')
        
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        
        # Callbacks for handling messages
        self.audio_callback: Optional[Callable[[str, bytes], None]] = None
        self.wake_callback: Optional[Callable[[str, dict], None]] = None
        self.audio_info_callback: Optional[Callable[[str, dict], None]] = None
        
        logger.info(
            f"MQTTSubscriber initialized: broker={broker}:{port}, "
            f"audio_topic={self.audio_topic}, meta_topic={self.meta_topic}, "
            f"audio_info_topic={self.audio_info_topic}"
        )
    
    def set_audio_callback(self, callback: Callable[[str, bytes], None]) -> None:
        """Set callback for handling audio data with assistant ID."""
        self.audio_callback = callback
    
    def set_wake_callback(self, callback: Callable[[str, dict], None]) -> None:
        """Set callback for handling wake word events with assistant ID."""
        self.wake_callback = callback
    
    def set_audio_info_callback(self, callback: Callable[[str, dict], None]) -> None:
        """Set callback for handling audio info configuration with assistant ID."""
        self.audio_info_callback = callback
    
    def connect(self) -> bool:
        """
        Connect to MQTT broker and subscribe to topics.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client = mqtt.Client(
                client_id=self.client_id,
                callback_api_version=mqtt.CallbackAPIVersion.VERSION1
            )
            
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
            client.subscribe(self.audio_info_topic, qos=1)
            logger.info(
                f"Subscribed to {self.audio_topic}, {self.meta_topic}, "
                f"and {self.audio_info_topic}"
            )
        else:
            logger.error(f"Failed to connect to MQTT broker: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when client disconnects from broker."""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected MQTT disconnect: {rc}")
        else:
            logger.info("MQTT Subscriber disconnected from broker")
    
    def _extract_assistant_id(self, topic: str, base_topic: str) -> Optional[str]:
        """
        Extract assistant ID from topic path.
        
        Args:
            topic: Full MQTT topic (e.g., "satellite1/audio_debug/pcm/assistant1")
            base_topic: Base topic path (e.g., "satellite1/audio_debug/pcm")
        
        Returns:
            Assistant ID or None if not found
        """
        # Remove base topic prefix and extract the ID
        if topic.startswith(base_topic + '/'):
            assistant_id = topic[len(base_topic) + 1:]
            # For audio_info topic, extract ID from pattern: base/ID/audio_info
            if assistant_id.endswith('/audio_info'):
                assistant_id = assistant_id[:-len('/audio_info')]
            return assistant_id if assistant_id else None
        return None
    
    def _on_message(self, client, userdata, msg):
        """Callback for when a message is received."""
        try:
            # Check if this is an audio_info topic
            if msg.topic.endswith('/audio_info'):
                # Extract assistant ID from topic
                assistant_id = self._extract_assistant_id(msg.topic, self.meta_topic_base)
                if not assistant_id:
                    logger.warning(f"Could not extract assistant ID from audio_info topic: {msg.topic}")
                    return
                
                # Handle audio info configuration
                if self.audio_info_callback:
                    try:
                        # Parse JSON audio info
                        audio_info = json.loads(msg.payload)
                        logger.info(f"Received audio info for assistant {assistant_id}: {audio_info}")
                        self.audio_info_callback(assistant_id, audio_info)
                    except Exception as e:
                        logger.error(f"Error parsing audio info for assistant {assistant_id}: {e}")
                else:
                    logger.warning("Received audio info but no callback set")
            
            # Check if this is an audio topic
            elif msg.topic.startswith(self.audio_topic_base):
                # Extract assistant ID from topic
                assistant_id = self._extract_assistant_id(msg.topic, self.audio_topic_base)
                if not assistant_id:
                    logger.warning(f"Could not extract assistant ID from topic: {msg.topic}")
                    return
                
                # Handle audio data (base64 encoded)
                if self.audio_callback:
                    try:
                        # Decode base64 audio data
                        audio_data = base64.b64decode(msg.payload)
                        self.audio_callback(assistant_id, audio_data)
                    except Exception as e:
                        logger.error(f"Error decoding audio data for assistant {assistant_id}: {e}")
                else:
                    logger.warning("Received audio data but no callback set")
            
            # Check if this is a meta topic (but not audio_info)
            elif msg.topic.startswith(self.meta_topic_base):
                # Extract assistant ID from topic
                assistant_id = self._extract_assistant_id(msg.topic, self.meta_topic_base)
                if not assistant_id:
                    logger.warning(f"Could not extract assistant ID from topic: {msg.topic}")
                    return
                
                # Handle wake word metadata
                if self.wake_callback:
                    try:
                        # Parse JSON metadata
                        metadata = json.loads(msg.payload)
                        self.wake_callback(assistant_id, metadata)
                    except Exception as e:
                        logger.error(f"Error parsing wake metadata for assistant {assistant_id}: {e}")
                else:
                    logger.warning("Received wake metadata but no callback set")
        
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
