"""Unit tests for MQTTPublisher class."""
import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from ingest_service.app.mqtt_publisher import MQTTPublisher


class TestMQTTPublisher:
    """Test cases for MQTTPublisher."""
    
    def test_init_with_defaults(self):
        """Test publisher initialization with default settings."""
        publisher = MQTTPublisher(
            broker="test-broker",
            port=1883,
            topic_prefix="test/topic"
        )
        
        assert publisher.broker == "test-broker"
        assert publisher.port == 1883
        assert publisher.topic_prefix == "test/topic"
        assert publisher.connected is False
    
    def test_init_with_credentials(self):
        """Test publisher initialization with authentication."""
        publisher = MQTTPublisher(
            broker="test-broker",
            username="testuser",
            password="testpass"
        )
        
        assert publisher.username == "testuser"
        assert publisher.password == "testpass"
    
    @patch('ingest_service.app.mqtt_publisher.mqtt.Client')
    def test_connect_success(self, mock_mqtt_client):
        """Test successful connection to MQTT broker."""
        mock_client_instance = Mock()
        mock_mqtt_client.return_value = mock_client_instance
        
        publisher = MQTTPublisher(broker="test-broker")
        result = publisher.connect()
        
        assert result is True
        mock_client_instance.connect.assert_called_once()
        mock_client_instance.loop_start.assert_called_once()
    
    @patch('ingest_service.app.mqtt_publisher.mqtt.Client')
    def test_connect_with_credentials(self, mock_mqtt_client):
        """Test connection with username and password."""
        mock_client_instance = Mock()
        mock_mqtt_client.return_value = mock_client_instance
        
        publisher = MQTTPublisher(
            broker="test-broker",
            username="user",
            password="pass"
        )
        publisher.connect()
        
        mock_client_instance.username_pw_set.assert_called_once_with("user", "pass")
    
    @patch('ingest_service.app.mqtt_publisher.mqtt.Client')
    def test_connect_failure(self, mock_mqtt_client):
        """Test connection failure handling."""
        mock_client_instance = Mock()
        mock_client_instance.connect.side_effect = Exception("Connection failed")
        mock_mqtt_client.return_value = mock_client_instance
        
        publisher = MQTTPublisher(broker="test-broker")
        result = publisher.connect()
        
        assert result is False
    
    @patch('ingest_service.app.mqtt_publisher.mqtt.Client')
    def test_disconnect(self, mock_mqtt_client):
        """Test disconnection from MQTT broker."""
        mock_client_instance = Mock()
        mock_mqtt_client.return_value = mock_client_instance
        
        publisher = MQTTPublisher(broker="test-broker")
        publisher.connect()
        publisher.disconnect()
        
        mock_client_instance.loop_stop.assert_called_once()
        mock_client_instance.disconnect.assert_called_once()
        assert publisher.connected is False
    
    @patch('ingest_service.app.mqtt_publisher.mqtt.Client')
    def test_publish_wake_event_success(self, mock_mqtt_client):
        """Test publishing wake event successfully."""
        mock_client_instance = Mock()
        mock_result = Mock()
        mock_result.rc = 0  # MQTT_ERR_SUCCESS
        mock_client_instance.publish.return_value = mock_result
        mock_mqtt_client.return_value = mock_client_instance
        
        publisher = MQTTPublisher(broker="test-broker", topic_prefix="test")
        publisher.connect()
        publisher.connected = True
        
        result = publisher.publish_wake_event(
            wav_path="/path/to/file.wav",
            metadata={"timestamp": "2024-01-01T00:00:00"}
        )
        
        assert result is True
        mock_client_instance.publish.assert_called_once()
        
        # Verify published message content
        call_args = mock_client_instance.publish.call_args
        topic = call_args[0][0]
        payload = json.loads(call_args[0][1])
        
        assert topic == "test/event"
        assert payload["event_type"] == "wake_word_detected"
        assert payload["wav_file"] == "/path/to/file.wav"
        assert payload["timestamp"] == "2024-01-01T00:00:00"
    
    @patch('ingest_service.app.mqtt_publisher.mqtt.Client')
    def test_publish_wake_event_not_connected(self, mock_mqtt_client):
        """Test publishing when not connected attempts reconnection."""
        mock_client_instance = Mock()
        mock_mqtt_client.return_value = mock_client_instance
        
        publisher = MQTTPublisher(broker="test-broker")
        publisher.connected = False
        
        # Mock connect failure
        with patch.object(publisher, 'connect', return_value=False):
            result = publisher.publish_wake_event("/path/to/file.wav")
        
        assert result is False
    
    @patch('ingest_service.app.mqtt_publisher.mqtt.Client')
    def test_publish_wake_event_failure(self, mock_mqtt_client):
        """Test handling of publish failure."""
        mock_client_instance = Mock()
        mock_result = Mock()
        mock_result.rc = 1  # Error code
        mock_client_instance.publish.return_value = mock_result
        mock_mqtt_client.return_value = mock_client_instance
        
        publisher = MQTTPublisher(broker="test-broker")
        publisher.connect()
        publisher.connected = True
        
        result = publisher.publish_wake_event("/path/to/file.wav")
        
        assert result is False
    
    @patch('ingest_service.app.mqtt_publisher.mqtt.Client')
    def test_publish_discovery_config(self, mock_mqtt_client):
        """Test publishing Home Assistant discovery configuration."""
        mock_client_instance = Mock()
        mock_result = Mock()
        mock_result.rc = 0
        mock_client_instance.publish.return_value = mock_result
        mock_mqtt_client.return_value = mock_client_instance
        
        publisher = MQTTPublisher(
            broker="test-broker",
            client_id="test-client",
            topic_prefix="test"
        )
        publisher.connect()
        publisher.connected = True
        
        publisher.publish_discovery_config(device_name="Test Device")
        
        # Verify discovery message was published
        mock_client_instance.publish.assert_called()
        
        # Check discovery topic format
        call_args = mock_client_instance.publish.call_args
        topic = call_args[0][0]
        payload = json.loads(call_args[0][1])
        
        assert "homeassistant/binary_sensor" in topic
        assert payload["name"] == "Test Device Wake Event"
        assert payload["unique_id"] == "test-client_wake_event"
    
    def test_on_connect_callback(self):
        """Test on_connect callback behavior."""
        publisher = MQTTPublisher(broker="test-broker")
        
        # Simulate successful connection
        publisher._on_connect(None, None, None, 0)
        
        assert publisher.connected is True
    
    def test_on_connect_callback_failure(self):
        """Test on_connect callback with connection failure."""
        publisher = MQTTPublisher(broker="test-broker")
        
        # Simulate connection failure (rc != 0)
        publisher._on_connect(None, None, None, 1)
        
        assert publisher.connected is False
    
    def test_on_disconnect_callback(self):
        """Test on_disconnect callback behavior."""
        publisher = MQTTPublisher(broker="test-broker")
        publisher.connected = True
        
        # Simulate disconnect
        publisher._on_disconnect(None, None, 0)
        
        assert publisher.connected is False
    
    def test_on_disconnect_callback_unexpected(self):
        """Test on_disconnect callback with unexpected disconnect."""
        publisher = MQTTPublisher(broker="test-broker")
        publisher.connected = True
        
        # Simulate unexpected disconnect (rc != 0)
        publisher._on_disconnect(None, None, 1)
        
        assert publisher.connected is False
    
    @patch('ingest_service.app.mqtt_publisher.mqtt.Client')
    def test_publish_with_qos_and_retain(self, mock_mqtt_client):
        """Test that messages are published with correct QoS and retain settings."""
        mock_client_instance = Mock()
        mock_result = Mock()
        mock_result.rc = 0
        mock_client_instance.publish.return_value = mock_result
        mock_mqtt_client.return_value = mock_client_instance
        
        publisher = MQTTPublisher(broker="test-broker")
        publisher.connect()
        publisher.connected = True
        
        publisher.publish_wake_event("/path/to/file.wav")
        
        # Check QoS and retain flags
        call_kwargs = mock_client_instance.publish.call_args[1]
        assert call_kwargs['qos'] == 1
        assert call_kwargs['retain'] is False
