"""Unit tests for multi-assistant functionality."""
import pytest
import numpy as np
from ingest_service.app.audio_buffer import MultiAssistantAudioBuffer
from ingest_service.app.mqtt_subscriber import MQTTSubscriber


@pytest.mark.asyncio
class TestMultiAssistantAudioBuffer:
    """Test cases for MultiAssistantAudioBuffer."""
    
    async def test_init(self):
        """Test multi-assistant buffer initialization."""
        buffer = MultiAssistantAudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=10.0)
        
        assert buffer.sample_rate == 16000
        assert buffer.buffer_duration == 10.0
        assert len(buffer.buffers) == 0
        assert buffer.get_assistant_ids() == []
    
    async def test_get_buffer_creates_new_buffer(self):
        """Test that get_buffer creates a new buffer for unknown assistant."""
        buffer = MultiAssistantAudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=10.0)
        
        assistant_buffer = await buffer.get_buffer("assistant1")
        
        assert assistant_buffer is not None
        assert "assistant1" in buffer.buffers
        assert buffer.get_assistant_ids() == ["assistant1"]
    
    async def test_get_buffer_returns_existing_buffer(self):
        """Test that get_buffer returns existing buffer for known assistant."""
        buffer = MultiAssistantAudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=10.0)
        
        assistant_buffer1 = await buffer.get_buffer("assistant1")
        assistant_buffer2 = await buffer.get_buffer("assistant1")
        
        assert assistant_buffer1 is assistant_buffer2
    
    async def test_append_audio_to_specific_assistant(self):
        """Test appending audio data to a specific assistant's buffer."""
        buffer = MultiAssistantAudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=1.0)
        
        # Create test audio data
        test_data1 = np.array([i for i in range(100)], dtype=np.int16)
        test_data2 = np.array([i + 1000 for i in range(100)], dtype=np.int16)
        
        # Append to different assistants
        await buffer.append("assistant1", test_data1.tobytes())
        await buffer.append("assistant2", test_data2.tobytes())
        
        # Verify both assistants have their own buffers
        assert "assistant1" in buffer.buffers
        assert "assistant2" in buffer.buffers
        assert buffer.buffers["assistant1"].get_buffer_size() == 100
        assert buffer.buffers["assistant2"].get_buffer_size() == 100
    
    async def test_get_clip_from_specific_assistant(self):
        """Test extracting clip from a specific assistant's buffer."""
        buffer = MultiAssistantAudioBuffer(sample_rate=100, sample_width=2, buffer_duration=10.0)
        
        # Add data to assistant1
        test_data = np.array([i for i in range(500)], dtype=np.int16)
        await buffer.append("assistant1", test_data.tobytes())
        
        # Get clip from assistant1
        clip = await buffer.get_clip("assistant1", pre_duration=1.0, post_duration=1.0)
        
        assert clip is not None
        assert len(clip) == 100  # Only pre_samples when trigger at end
    
    async def test_clear_specific_assistant_buffer(self):
        """Test clearing a specific assistant's buffer."""
        buffer = MultiAssistantAudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=1.0)
        
        # Add data to both assistants
        test_data = np.array([i for i in range(100)], dtype=np.int16)
        await buffer.append("assistant1", test_data.tobytes())
        await buffer.append("assistant2", test_data.tobytes())
        
        # Clear assistant1
        await buffer.clear("assistant1")
        
        # Verify assistant1 is cleared, assistant2 is not
        assert buffer.buffers["assistant1"].get_buffer_size() == 0
        assert buffer.buffers["assistant2"].get_buffer_size() == 100
    
    async def test_clear_all_buffers(self):
        """Test clearing all assistant buffers."""
        buffer = MultiAssistantAudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=1.0)
        
        # Add data to multiple assistants
        test_data = np.array([i for i in range(100)], dtype=np.int16)
        await buffer.append("assistant1", test_data.tobytes())
        await buffer.append("assistant2", test_data.tobytes())
        await buffer.append("assistant3", test_data.tobytes())
        
        # Clear all
        await buffer.clear(None)
        
        # Verify all are cleared
        assert buffer.buffers["assistant1"].get_buffer_size() == 0
        assert buffer.buffers["assistant2"].get_buffer_size() == 0
        assert buffer.buffers["assistant3"].get_buffer_size() == 0
    
    async def test_get_buffer_size_for_specific_assistant(self):
        """Test getting buffer size for specific assistant."""
        buffer = MultiAssistantAudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=1.0)
        
        test_data1 = np.array([i for i in range(100)], dtype=np.int16)
        test_data2 = np.array([i for i in range(200)], dtype=np.int16)
        
        await buffer.append("assistant1", test_data1.tobytes())
        await buffer.append("assistant2", test_data2.tobytes())
        
        assert buffer.get_buffer_size("assistant1") == 100
        assert buffer.get_buffer_size("assistant2") == 200
    
    async def test_get_buffer_size_total(self):
        """Test getting total buffer size across all assistants."""
        buffer = MultiAssistantAudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=1.0)
        
        test_data1 = np.array([i for i in range(100)], dtype=np.int16)
        test_data2 = np.array([i for i in range(200)], dtype=np.int16)
        
        await buffer.append("assistant1", test_data1.tobytes())
        await buffer.append("assistant2", test_data2.tobytes())
        
        assert buffer.get_buffer_size() == 300
    
    async def test_get_assistant_ids(self):
        """Test getting list of active assistant IDs."""
        buffer = MultiAssistantAudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=1.0)
        
        test_data = np.array([i for i in range(100)], dtype=np.int16)
        await buffer.append("assistant1", test_data.tobytes())
        await buffer.append("assistant2", test_data.tobytes())
        await buffer.append("assistant3", test_data.tobytes())
        
        assistant_ids = buffer.get_assistant_ids()
        assert len(assistant_ids) == 3
        assert "assistant1" in assistant_ids
        assert "assistant2" in assistant_ids
        assert "assistant3" in assistant_ids


class TestMQTTSubscriberMultiAssistant:
    """Test cases for MQTT subscriber with multi-assistant support."""
    
    def test_init_appends_wildcard_to_topics(self):
        """Test that subscriber adds wildcard to topics."""
        subscriber = MQTTSubscriber(
            audio_topic="satellite1/audio_debug/pcm",
            meta_topic="satellite1/audio_debug/meta"
        )
        
        assert subscriber.audio_topic == "satellite1/audio_debug/pcm/+"
        assert subscriber.meta_topic == "satellite1/audio_debug/meta/+"
    
    def test_init_preserves_existing_wildcard(self):
        """Test that subscriber preserves existing wildcard."""
        subscriber = MQTTSubscriber(
            audio_topic="satellite1/audio_debug/pcm/+",
            meta_topic="satellite1/audio_debug/meta/+"
        )
        
        assert subscriber.audio_topic == "satellite1/audio_debug/pcm/+"
        assert subscriber.meta_topic == "satellite1/audio_debug/meta/+"
    
    def test_extract_assistant_id_from_audio_topic(self):
        """Test extracting assistant ID from audio topic."""
        subscriber = MQTTSubscriber(
            audio_topic="satellite1/audio_debug/pcm"
        )
        
        assistant_id = subscriber._extract_assistant_id(
            "satellite1/audio_debug/pcm/assistant1",
            "satellite1/audio_debug/pcm"
        )
        
        assert assistant_id == "assistant1"
    
    def test_extract_assistant_id_from_meta_topic(self):
        """Test extracting assistant ID from meta topic."""
        subscriber = MQTTSubscriber(
            meta_topic="satellite1/audio_debug/meta"
        )
        
        assistant_id = subscriber._extract_assistant_id(
            "satellite1/audio_debug/meta/assistant2",
            "satellite1/audio_debug/meta"
        )
        
        assert assistant_id == "assistant2"
    
    def test_extract_assistant_id_missing(self):
        """Test extracting assistant ID when not present."""
        subscriber = MQTTSubscriber(
            audio_topic="satellite1/audio_debug/pcm"
        )
        
        assistant_id = subscriber._extract_assistant_id(
            "satellite1/audio_debug/pcm",
            "satellite1/audio_debug/pcm"
        )
        
        assert assistant_id is None
    
    def test_extract_assistant_id_wrong_base(self):
        """Test extracting assistant ID with wrong base topic."""
        subscriber = MQTTSubscriber(
            audio_topic="satellite1/audio_debug/pcm"
        )
        
        assistant_id = subscriber._extract_assistant_id(
            "satellite2/audio_debug/pcm/assistant1",
            "satellite1/audio_debug/pcm"
        )
        
        assert assistant_id is None
