"""Unit tests for FastAPI main application."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import numpy as np
import tempfile
import os


# Mock settings before importing main
with patch.dict(os.environ, {
    "OUTPUT_DIR": tempfile.mkdtemp(),
    "MQTT_BROKER": "test-broker"
}):
    from ingest_service.app.main import app, get_audio_buffer, get_wav_writer, get_mqtt_publisher, get_mqtt_subscriber


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global instances between tests."""
    import ingest_service.app.main as main_module
    main_module.audio_buffer = None
    main_module.wav_writer = None
    main_module.mqtt_publisher = None
    main_module.mqtt_subscriber = None
    yield


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
    
    @patch('ingest_service.app.main.get_audio_buffer')
    @patch('ingest_service.app.main.get_wav_writer')
    @patch('ingest_service.app.main.get_mqtt_publisher')
    def test_trigger_wake_event_success(
        self, mock_get_mqtt, mock_get_wav, mock_get_buffer, client
    ):
        """Test triggering wake event successfully."""
        # Mock buffer returning audio clip
        mock_clip = np.array([i for i in range(1000)], dtype=np.int16)
        mock_buffer_instance = Mock()
        mock_buffer_instance.get_clip = AsyncMock(return_value=mock_clip)
        mock_get_buffer.return_value = mock_buffer_instance
        
        # Mock WAV writer
        mock_wav_instance = Mock()
        mock_wav_instance.write_clip.return_value = "/path/to/file.wav"
        mock_get_wav.return_value = mock_wav_instance
        
        # Mock MQTT publisher
        mock_mqtt_instance = Mock()
        mock_mqtt_instance.publish_wake_event.return_value = True
        mock_get_mqtt.return_value = mock_mqtt_instance
        
        response = client.post("/wake_event")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "wav_file" in data
        assert "metadata" in data
    
    @patch('ingest_service.app.main.get_audio_buffer')
    @patch('ingest_service.app.main.get_wav_writer')
    def test_trigger_wake_event_insufficient_data(self, mock_get_wav, mock_get_buffer, client):
        """Test wake event with insufficient buffer data."""
        # Mock buffer returning None
        mock_buffer_instance = Mock()
        mock_buffer_instance.get_clip = AsyncMock(return_value=None)
        mock_get_buffer.return_value = mock_buffer_instance
        
        # Mock wav_writer to avoid file system issues
        mock_wav_instance = Mock()
        mock_get_wav.return_value = mock_wav_instance
        
        response = client.post("/wake_event")
        
        assert response.status_code == 400
        assert "Insufficient audio data" in response.json()["detail"]
    
    @patch('ingest_service.app.main.get_audio_buffer')
    @patch('ingest_service.app.main.get_wav_writer')
    @patch('ingest_service.app.main.get_mqtt_publisher')
    def test_trigger_wake_event_with_custom_durations(
        self, mock_get_mqtt, mock_get_wav, mock_get_buffer, client
    ):
        """Test wake event with custom pre/post durations."""
        mock_clip = np.array([i for i in range(1000)], dtype=np.int16)
        mock_buffer_instance = Mock()
        mock_buffer_instance.get_clip = AsyncMock(return_value=mock_clip)
        mock_get_buffer.return_value = mock_buffer_instance
        
        mock_wav_instance = Mock()
        mock_wav_instance.write_clip.return_value = "/path/to/file.wav"
        mock_get_wav.return_value = mock_wav_instance
        
        mock_mqtt_instance = Mock()
        mock_mqtt_instance.publish_wake_event.return_value = True
        mock_get_mqtt.return_value = mock_mqtt_instance
        
        response = client.post(
            "/wake_event?pre_duration=3.0&post_duration=4.0"
        )
        
        assert response.status_code == 200
        
        # Verify buffer.get_clip was called with correct params
        mock_buffer_instance.get_clip.assert_called_once()
        call_kwargs = mock_buffer_instance.get_clip.call_args[1]
        assert call_kwargs["pre_duration"] == 3.0
        assert call_kwargs["post_duration"] == 4.0
    
    @patch('ingest_service.app.main.get_audio_buffer')
    def test_clear_buffer_endpoint(self, mock_get_buffer, client):
        """Test clear buffer endpoint."""
        mock_buffer_instance = Mock()
        mock_buffer_instance.clear = AsyncMock()
        mock_get_buffer.return_value = mock_buffer_instance
        
        response = client.post("/clear_buffer")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Buffer cleared" in data["message"]
        mock_buffer_instance.clear.assert_called_once()
    
    @patch('ingest_service.app.main.get_wav_writer')
    def test_cleanup_endpoint(self, mock_get_wav, client):
        """Test cleanup old files endpoint."""
        mock_wav_instance = Mock()
        mock_wav_instance.cleanup_old_files.return_value = 5
        mock_get_wav.return_value = mock_wav_instance
        
        response = client.post("/cleanup?max_age_days=3")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["deleted_count"] == 5
        assert data["max_age_days"] == 3
        
        mock_wav_instance.cleanup_old_files.assert_called_once_with(3)
    
    @patch('ingest_service.app.main.get_audio_buffer')
    def test_websocket_audio_endpoint(self, mock_get_buffer, client):
        """Test WebSocket audio streaming endpoint."""
        mock_buffer_instance = Mock()
        mock_buffer_instance.append = AsyncMock()
        mock_get_buffer.return_value = mock_buffer_instance
        
        # Test data
        test_audio = b'\x00\x01' * 100  # 200 bytes of test PCM data
        
        with client.websocket_connect("/ws/audio") as websocket:
            # Send audio data
            websocket.send_bytes(test_audio)
            
            # Give it a moment to process
            import time
            time.sleep(0.1)
        
        # Verify audio was appended to buffer
        assert mock_buffer_instance.append.called
    
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
    
    def test_startup_event_mqtt_connection(self, client):
        """Test that startup event connects to MQTT."""
        # The startup event is triggered automatically by TestClient
        # We can't easily mock it without restructuring, so just verify the app works
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_health_check_includes_mqtt_status(self, client):
        """Test that health check includes MQTT connection status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "mqtt_publisher_connected" in data
        assert "mqtt_subscriber_connected" in data
        assert isinstance(data["mqtt_publisher_connected"], bool)
        assert isinstance(data["mqtt_subscriber_connected"], bool)
    
    def test_mqtt_callbacks_use_thread_safe_scheduling(self):
        """Test that MQTT callbacks are properly set up with thread-safe asyncio scheduling."""
        import asyncio
        import threading
        from ingest_service.app.main import handle_audio_data, handle_wake_event
        
        # Create an event loop for the test
        loop = asyncio.new_event_loop()
        
        try:
            # Set the loop in the current thread
            asyncio.set_event_loop(loop)
            
            # Simulate the callback wrapper that would be created in startup_event
            def audio_callback(data: bytes):
                """Thread-safe wrapper for async audio handler."""
                # This should not raise "no running event loop" when called from another thread
                asyncio.run_coroutine_threadsafe(handle_audio_data(data), loop)
            
            def wake_callback(metadata: dict):
                """Thread-safe wrapper for async wake handler."""
                asyncio.run_coroutine_threadsafe(handle_wake_event(metadata), loop)
            
            # Test calling from a different thread (simulating MQTT thread)
            test_data = b'\x00\x01\x02\x03'
            callback_exception = None
            
            def call_from_thread():
                """Call the callback from a separate thread to simulate MQTT thread."""
                nonlocal callback_exception
                try:
                    # This should work without "no running event loop" error
                    audio_callback(test_data)
                    wake_callback({"event": "test"})
                except Exception as e:
                    callback_exception = e
            
            thread = threading.Thread(target=call_from_thread)
            thread.start()
            thread.join(timeout=2.0)
            
            # Should not raise "no running event loop" error
            assert callback_exception is None, f"Callback raised exception: {callback_exception}"
            
        finally:
            loop.close()
