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
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=10.0)
        
        assert buffer.default_sample_rate == 16000
        assert buffer.buffer_duration == 10.0
        assert len(buffer.buffers) == 0
        assert buffer.get_assistant_ids() == []
    
    async def test_get_buffer_creates_new_buffer(self):
        """Test that get_buffer creates a new buffer for unknown assistant."""
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=10.0)
        
        assistant_buffer = await buffer.get_buffer("assistant1")
        
        assert assistant_buffer is not None
        assert "assistant1" in buffer.buffers
        assert buffer.get_assistant_ids() == ["assistant1"]
    
    async def test_get_buffer_returns_existing_buffer(self):
        """Test that get_buffer returns existing buffer for known assistant."""
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=10.0)
        
        assistant_buffer1 = await buffer.get_buffer("assistant1")
        assistant_buffer2 = await buffer.get_buffer("assistant1")
        
        assert assistant_buffer1 is assistant_buffer2
    
    async def test_append_audio_to_specific_assistant(self):
        """Test appending audio data to a specific assistant's buffer."""
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=1.0)
        
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
        buffer = MultiAssistantAudioBuffer(default_sample_rate=100, default_sample_width=2, buffer_duration=10.0)
        
        # Add data to assistant1
        test_data = np.array([i for i in range(500)], dtype=np.int16)
        await buffer.append("assistant1", test_data.tobytes())
        
        # Get clip from assistant1
        clip = await buffer.get_clip("assistant1", pre_duration=1.0, post_duration=1.0)
        
        assert clip is not None
        assert len(clip) == 100  # Only pre_samples when trigger at end
    
    async def test_clear_specific_assistant_buffer(self):
        """Test clearing a specific assistant's buffer."""
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=1.0)
        
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
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=1.0)
        
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
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=1.0)
        
        test_data1 = np.array([i for i in range(100)], dtype=np.int16)
        test_data2 = np.array([i for i in range(200)], dtype=np.int16)
        
        await buffer.append("assistant1", test_data1.tobytes())
        await buffer.append("assistant2", test_data2.tobytes())
        
        assert buffer.get_buffer_size("assistant1") == 100
        assert buffer.get_buffer_size("assistant2") == 200
    
    async def test_get_buffer_size_total(self):
        """Test getting total buffer size across all assistants."""
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=1.0)
        
        test_data1 = np.array([i for i in range(100)], dtype=np.int16)
        test_data2 = np.array([i for i in range(200)], dtype=np.int16)
        
        await buffer.append("assistant1", test_data1.tobytes())
        await buffer.append("assistant2", test_data2.tobytes())
        
        assert buffer.get_buffer_size() == 300
    
    async def test_get_assistant_ids(self):
        """Test getting list of active assistant IDs."""
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=1.0)
        
        test_data = np.array([i for i in range(100)], dtype=np.int16)
        await buffer.append("assistant1", test_data.tobytes())
        await buffer.append("assistant2", test_data.tobytes())
        await buffer.append("assistant3", test_data.tobytes())
        
        assistant_ids = buffer.get_assistant_ids()
        assert len(assistant_ids) == 3
        assert "assistant1" in assistant_ids
        assert "assistant2" in assistant_ids
        assert "assistant3" in assistant_ids
    
    async def test_set_audio_config(self):
        """Test setting audio configuration for a specific assistant."""
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=1.0)
        
        # Set custom config for assistant1
        await buffer.set_audio_config("assistant1", sample_rate=48000, bits_per_sample=32, channels=2)
        
        # Verify config was stored
        assert "assistant1" in buffer.assistant_configs
        config = buffer.assistant_configs["assistant1"]
        assert config["sample_rate"] == 48000
        assert config["sample_width"] == 4  # 32 bits / 8 = 4 bytes
        assert config["channels"] == 2
        
        # Verify buffer was created with correct config
        assert "assistant1" in buffer.buffers
    
    async def test_get_buffer_uses_custom_config(self):
        """Test that get_buffer uses custom config when available."""
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=1.0)
        
        # Set custom config before getting buffer
        await buffer.set_audio_config("assistant1", sample_rate=48000, bits_per_sample=32, channels=2)
        
        # Get buffer should use custom config
        assistant_buffer = await buffer.get_buffer("assistant1")
        assert assistant_buffer.sample_rate == 48000
        assert assistant_buffer.sample_width == 4
        assert assistant_buffer.channels == 2
    
    async def test_get_buffer_uses_defaults_without_config(self):
        """Test that get_buffer uses defaults when no custom config exists."""
        buffer = MultiAssistantAudioBuffer(default_sample_rate=16000, default_sample_width=2, buffer_duration=1.0)
        
        # Get buffer without setting config should use defaults
        assistant_buffer = await buffer.get_buffer("assistant2")
        assert assistant_buffer.sample_rate == 16000
        assert assistant_buffer.sample_width == 2


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
    
    def test_extract_assistant_id_from_audio_info_topic(self):
        """Test extracting assistant ID from audio_info topic."""
        subscriber = MQTTSubscriber(
            meta_topic="satellite1/audio_debug/meta"
        )
        
        assistant_id = subscriber._extract_assistant_id(
            "satellite1/audio_debug/meta/assistant1/audio_info",
            "satellite1/audio_debug/meta"
        )
        
        assert assistant_id == "assistant1"
    
    def test_audio_info_topic_initialization(self):
        """Test that audio_info topic is properly initialized."""
        subscriber = MQTTSubscriber(
            meta_topic="satellite1/audio_debug/meta"
        )
        
        assert subscriber.audio_info_topic == "satellite1/audio_debug/meta/+/audio_info"
