"""Unit tests for wake event timing to ensure post-wake samples are captured."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio
import numpy as np
import tempfile
import os

# Test constant for POST_WAKE_DURATION_SECONDS
TEST_POST_WAKE_DURATION = 3.0

# Mock settings before importing main
with patch.dict(os.environ, {
    "OUTPUT_DIR": tempfile.mkdtemp(),
    "MQTT_BROKER": "test-broker",
    "POST_WAKE_DURATION_SECONDS": str(TEST_POST_WAKE_DURATION)
}):
    from ingest_service.app.main import handle_wake_event, get_audio_buffer, get_wav_writer, get_mqtt_publisher
    from ingest_service.app.config import settings


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global instances between tests."""
    import ingest_service.app.main as main_module
    main_module.audio_buffer = None
    main_module.wav_writer = None
    main_module.mqtt_publisher = None
    main_module.mqtt_subscriber = None
    yield


@pytest.mark.asyncio
class TestWakeEventTiming:
    """Test cases to verify wake event waits for post-wake samples."""
    
    @patch('ingest_service.app.main.asyncio.sleep')
    @patch('ingest_service.app.main.get_audio_buffer')
    @patch('ingest_service.app.main.get_wav_writer')
    @patch('ingest_service.app.main.get_mqtt_publisher')
    async def test_handle_wake_event_waits_for_post_duration(
        self, mock_get_mqtt, mock_get_wav, mock_get_buffer, mock_sleep
    ):
        """Test that handle_wake_event waits POST_WAKE_DURATION_SECONDS before extracting clip."""
        # Set up mocks
        mock_clip = np.array([i for i in range(1000)], dtype=np.int16)
        mock_buffer_instance = Mock()
        mock_buffer_instance.get_clip = AsyncMock(return_value=mock_clip)
        mock_buffer_instance.get_audio_config = Mock(return_value={
            "sample_rate": 48000,
            "sample_width": 4,
            "channels": 1
        })
        mock_get_buffer.return_value = mock_buffer_instance
        
        mock_wav_instance = Mock()
        mock_wav_instance.write_clip.return_value = "/path/to/file.wav"
        mock_get_wav.return_value = mock_wav_instance
        
        mock_mqtt_instance = Mock()
        mock_mqtt_instance.publish_wake_event.return_value = True
        mock_get_mqtt.return_value = mock_mqtt_instance
        
        # Mock asyncio.sleep to return immediately but track that it was called
        mock_sleep.return_value = None
        
        # Call handle_wake_event
        metadata = {"event": "wake"}
        await handle_wake_event("test_assistant", metadata)
        
        # Verify sleep was called with POST_WAKE_DURATION_SECONDS
        mock_sleep.assert_called_once()
        sleep_duration = mock_sleep.call_args[0][0]
        assert sleep_duration == TEST_POST_WAKE_DURATION, \
            f"Expected sleep({TEST_POST_WAKE_DURATION}) but got sleep({sleep_duration})"
        
        # Verify get_clip was called AFTER sleep with trigger_offset
        mock_buffer_instance.get_clip.assert_called_once()
        call_kwargs = mock_buffer_instance.get_clip.call_args[1]
        assert call_kwargs.get("trigger_offset") == TEST_POST_WAKE_DURATION, \
            f"Expected trigger_offset={TEST_POST_WAKE_DURATION} but got {call_kwargs.get('trigger_offset')}"
    
    @patch('ingest_service.app.main.asyncio.sleep')
    @patch('ingest_service.app.main.get_audio_buffer')
    @patch('ingest_service.app.main.get_wav_writer')
    @patch('ingest_service.app.main.get_mqtt_publisher')
    async def test_handle_wake_event_sleep_before_get_clip(
        self, mock_get_mqtt, mock_get_wav, mock_get_buffer, mock_sleep
    ):
        """Test that asyncio.sleep is called BEFORE buffer.get_clip to capture post-wake audio."""
        # Track call order
        call_order = []
        
        # Set up mocks with call tracking
        mock_clip = np.array([i for i in range(1000)], dtype=np.int16)
        mock_buffer_instance = Mock()
        
        async def track_get_clip(*args, **kwargs):
            call_order.append('get_clip')
            return mock_clip
        
        mock_buffer_instance.get_clip = track_get_clip
        mock_buffer_instance.get_audio_config = Mock(return_value={
            "sample_rate": 48000,
            "sample_width": 4,
            "channels": 1
        })
        mock_get_buffer.return_value = mock_buffer_instance
        
        mock_wav_instance = Mock()
        mock_wav_instance.write_clip.return_value = "/path/to/file.wav"
        mock_get_wav.return_value = mock_wav_instance
        
        mock_mqtt_instance = Mock()
        mock_mqtt_instance.publish_wake_event.return_value = True
        mock_get_mqtt.return_value = mock_mqtt_instance
        
        # Track sleep calls
        async def track_sleep(*args, **kwargs):
            call_order.append('sleep')
        
        mock_sleep.side_effect = track_sleep
        
        # Call handle_wake_event
        metadata = {"event": "wake"}
        await handle_wake_event("test_assistant", metadata)
        
        # Verify order: sleep should be called before get_clip
        assert 'sleep' in call_order, "asyncio.sleep was not called"
        assert 'get_clip' in call_order, "buffer.get_clip was not called"
        sleep_index = call_order.index('sleep')
        get_clip_index = call_order.index('get_clip')
        assert sleep_index < get_clip_index, \
            f"asyncio.sleep should be called BEFORE get_clip, but order was: {call_order}"
    
    @patch('ingest_service.app.main.asyncio.sleep')
    @patch('ingest_service.app.main.get_audio_buffer')
    @patch('ingest_service.app.main.get_wav_writer')
    @patch('ingest_service.app.main.get_mqtt_publisher')
    async def test_handle_wake_event_with_different_post_durations(
        self, mock_get_mqtt, mock_get_wav, mock_get_buffer, mock_sleep
    ):
        """Test that sleep duration matches POST_WAKE_DURATION_SECONDS setting."""
        # Set up mocks
        mock_clip = np.array([i for i in range(1000)], dtype=np.int16)
        mock_buffer_instance = Mock()
        mock_buffer_instance.get_clip = AsyncMock(return_value=mock_clip)
        mock_buffer_instance.get_audio_config = Mock(return_value={
            "sample_rate": 48000,
            "sample_width": 4,
            "channels": 1
        })
        mock_get_buffer.return_value = mock_buffer_instance
        
        mock_wav_instance = Mock()
        mock_wav_instance.write_clip.return_value = "/path/to/file.wav"
        mock_get_wav.return_value = mock_wav_instance
        
        mock_mqtt_instance = Mock()
        mock_mqtt_instance.publish_wake_event.return_value = True
        mock_get_mqtt.return_value = mock_mqtt_instance
        
        mock_sleep.return_value = None
        
        # Call handle_wake_event
        metadata = {"event": "wake"}
        await handle_wake_event("test_assistant", metadata)
        
        # Verify sleep was called
        mock_sleep.assert_called_once()
        
        # The sleep duration should come from settings.POST_WAKE_DURATION_SECONDS
        sleep_duration = mock_sleep.call_args[0][0]
        assert sleep_duration == settings.POST_WAKE_DURATION_SECONDS, \
            f"Expected sleep({settings.POST_WAKE_DURATION_SECONDS}) but got sleep({sleep_duration})"
    
    @patch('ingest_service.app.main.asyncio.sleep')
    @patch('ingest_service.app.main.get_audio_buffer')
    async def test_non_wake_event_does_not_sleep(
        self, mock_get_buffer, mock_sleep
    ):
        """Test that non-wake events don't trigger sleep or clip extraction."""
        mock_buffer_instance = Mock()
        mock_buffer_instance.get_clip = AsyncMock()
        mock_get_buffer.return_value = mock_buffer_instance
        
        mock_sleep.return_value = None
        
        # Call with non-wake event
        metadata = {"event": "other"}
        await handle_wake_event("test_assistant", metadata)
        
        # Verify sleep was NOT called for non-wake events
        mock_sleep.assert_not_called()
        
        # Verify get_clip was NOT called
        mock_buffer_instance.get_clip.assert_not_called()
