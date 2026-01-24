import json
import logging
from typing import Optional, Dict, Any
import paho.mqtt.client as mqtt

from .config import settings

logger = logging.getLogger(__name__)


class MQTTPublisher:
    """Handles MQTT publishing for wake word events."""
    
    def __init__(
        self,
        broker: str = settings.MQTT_BROKER,
        port: int = settings.MQTT_PORT,
        username: Optional[str] = settings.MQTT_USERNAME,
        password: Optional[str] = settings.MQTT_PASSWORD,
        client_id: str = settings.MQTT_CLIENT_ID,
        topic_prefix: str = settings.MQTT_TOPIC_PREFIX
    ):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id
        self.topic_prefix = topic_prefix
        
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        
        logger.info(
            f"MQTTPublisher initialized: broker={broker}:{port}, "
            f"topic_prefix={topic_prefix}"
        )
    
    def connect(self) -> bool:
        """
        Connect to MQTT broker.
        
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
            self.client.on_publish = self._on_publish
            
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
    
    def publish_wake_event(
        self,
        wav_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish a wake word event to MQTT.
        
        Args:
            wav_path: Path to the WAV file
            metadata: Optional metadata about the event
        
        Returns:
            True if publish successful, False otherwise
        """
        if not self.connected:
            logger.warning("Not connected to MQTT broker, attempting to connect...")
            if not self.connect():
                return False
        
        try:
            # Build event payload
            payload = {
                "event_type": "wake_word_detected",
                "wav_file": wav_path,
                "timestamp": metadata.get("timestamp") if metadata else None,
            }
            
            # Add any additional metadata
            if metadata:
                payload.update(metadata)
            
            # Publish to event topic
            topic = f"{self.topic_prefix}/event"
            result = self.client.publish(
                topic,
                json.dumps(payload),
                qos=1,
                retain=False
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Published wake event to {topic}")
                return True
            else:
                logger.error(f"Failed to publish wake event: {result.rc}")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing wake event: {e}")
            return False
    
    def publish_discovery_config(self, device_name: str = "Wake Word Debugger") -> None:
        """
        Publish Home Assistant MQTT discovery configuration.
        
        Args:
            device_name: Name of the device for Home Assistant
        """
        if not self.connected:
            logger.warning("Not connected to MQTT broker")
            return
        
        try:
            # Binary sensor for wake word detection
            discovery_topic = (
                f"{settings.HASS_DISCOVERY_PREFIX}/binary_sensor/"
                f"{self.client_id}/wake_event/config"
            )
            
            discovery_payload = {
                "name": f"{device_name} Wake Event",
                "unique_id": f"{self.client_id}_wake_event",
                "state_topic": f"{self.topic_prefix}/event",
                "value_template": "{{ 'ON' if value_json.event_type == 'wake_word_detected' else 'OFF' }}",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device_class": "sound",
                "device": {
                    "identifiers": [self.client_id],
                    "name": device_name,
                    "model": "Wake Word Debug Service",
                    "manufacturer": "Custom"
                }
            }
            
            result = self.client.publish(
                discovery_topic,
                json.dumps(discovery_payload),
                qos=1,
                retain=True
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("Published Home Assistant discovery config")
            else:
                logger.error(f"Failed to publish discovery config: {result.rc}")
                
        except Exception as e:
            logger.error(f"Error publishing discovery config: {e}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when client connects to broker."""
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            
            # Publish discovery config on connect
            self.publish_discovery_config()
        else:
            logger.error(f"Failed to connect to MQTT broker: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when client disconnects from broker."""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected MQTT disconnect: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")
    
    def _on_publish(self, client, userdata, mid):
        """Callback for when message is published."""
        logger.debug(f"Message published: {mid}")
