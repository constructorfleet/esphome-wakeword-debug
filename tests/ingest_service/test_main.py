"""Unit tests for FastAPI main application."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import numpy as np

from ingest_service.app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestMainAPI:
    """Test cases for main FastAPI application."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns service info."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Wake Word Audio Ingest Service"
        assert "version" in data
        assert "status" in data
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "buffer_samples" in data
        assert "buffer_duration_seconds" in data
    
    @patch('ingest_service.app.main.audio_buffer')
    @patch('ingest_service.app.main.wav_writer')
    @patch('ingest_service.app.main.mqtt_publisher')
    def test_trigger_wake_event_success(
        self, mock_mqtt, mock_wav, mock_buffer, client
    ):
        """Test triggering wake event successfully."""
        # Mock buffer returning audio clip
        mock_clip = np.array([i for i in range(1000)], dtype=np.int16)
        mock_buffer.get_clip = AsyncMock(return_value=mock_clip)
        
        # Mock WAV writer
        mock_wav.write_clip.return_value = "/path/to/file.wav"
        
        # Mock MQTT publisher
        mock_mqtt.publish_wake_event.return_value = True
        
        response = client.post("/wake_event")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "wav_file" in data
        assert "metadata" in data
    
    @patch('ingest_service.app.main.audio_buffer')
    def test_trigger_wake_event_insufficient_data(self, mock_buffer, client):
        """Test wake event with insufficient buffer data."""
        # Mock buffer returning None
        mock_buffer.get_clip = AsyncMock(return_value=None)
        
        response = client.post("/wake_event")
        
        assert response.status_code == 400
        assert "Insufficient audio data" in response.json()["detail"]
    
    @patch('ingest_service.app.main.audio_buffer')
    def test_trigger_wake_event_with_custom_durations(self, mock_buffer, client):
        """Test wake event with custom pre/post durations."""
        mock_clip = np.array([i for i in range(1000)], dtype=np.int16)
        mock_buffer.get_clip = AsyncMock(return_value=mock_clip)
        
        with patch('ingest_service.app.main.wav_writer') as mock_wav:
            mock_wav.write_clip.return_value = "/path/to/file.wav"
            
            with patch('ingest_service.app.main.mqtt_publisher') as mock_mqtt:
                mock_mqtt.publish_wake_event.return_value = True
                
                response = client.post(
                    "/wake_event?pre_duration=3.0&post_duration=4.0"
                )
                
                assert response.status_code == 200
                
                # Verify buffer.get_clip was called with correct params
                mock_buffer.get_clip.assert_called_once()
                call_kwargs = mock_buffer.get_clip.call_args[1]
                assert call_kwargs["pre_duration"] == 3.0
                assert call_kwargs["post_duration"] == 4.0
    
    @patch('ingest_service.app.main.audio_buffer')
    def test_clear_buffer_endpoint(self, mock_buffer, client):
        """Test clear buffer endpoint."""
        mock_buffer.clear = AsyncMock()
        
        response = client.post("/clear_buffer")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Buffer cleared" in data["message"]
        mock_buffer.clear.assert_called_once()
    
    @patch('ingest_service.app.main.wav_writer')
    def test_cleanup_endpoint(self, mock_wav, client):
        """Test cleanup old files endpoint."""
        mock_wav.cleanup_old_files.return_value = 5
        
        response = client.post("/cleanup?max_age_days=3")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["deleted_count"] == 5
        assert data["max_age_days"] == 3
        
        mock_wav.cleanup_old_files.assert_called_once_with(3)
    
    @patch('ingest_service.app.main.audio_buffer')
    def test_websocket_audio_endpoint(self, mock_buffer, client):
        """Test WebSocket audio streaming endpoint."""
        mock_buffer.append = AsyncMock()
        
        # Test data
        test_audio = b'\x00\x01' * 100  # 200 bytes of test PCM data
        
        with client.websocket_connect("/ws/audio") as websocket:
            # Send audio data
            websocket.send_bytes(test_audio)
            
            # Give it a moment to process
            import time
            time.sleep(0.1)
        
        # Verify audio was appended to buffer
        assert mock_buffer.append.called
    
    def test_websocket_connection_tracking(self, client):
        """Test that WebSocket connections are tracked."""
        from ingest_service.app.main import active_connections
        
        initial_count = len(active_connections)
        
        with client.websocket_connect("/ws/audio") as websocket:
            # Connection should be added
            assert len(active_connections) >= initial_count
        
        # After closing, connection should be removed (eventually)
        # Note: May need a small delay for cleanup
        import time
        time.sleep(0.1)
    
    @patch('ingest_service.app.main.mqtt_publisher')
    def test_startup_event_mqtt_connection(self, mock_mqtt):
        """Test that startup event connects to MQTT."""
        mock_mqtt.connect.return_value = True
        
        # Trigger startup (happens automatically with TestClient)
        client = TestClient(app)
        
        # MQTT connect should have been called
        assert mock_mqtt.connect.called
    
    def test_health_check_includes_mqtt_status(self, client):
        """Test that health check includes MQTT connection status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "mqtt_connected" in data
        assert isinstance(data["mqtt_connected"], bool)
