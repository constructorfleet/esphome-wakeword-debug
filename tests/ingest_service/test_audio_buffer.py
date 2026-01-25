"""Unit tests for AudioBuffer class."""
import pytest
import numpy as np
from ingest_service.app.audio_buffer import AudioBuffer


@pytest.mark.asyncio
class TestAudioBuffer:
    """Test cases for AudioBuffer."""
    
    async def test_init_default_params(self):
        """Test buffer initialization with default parameters."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=10.0)
        
        assert buffer.sample_rate == 16000
        assert buffer.buffer_duration == 10.0
        assert buffer.max_samples == 160000
        assert buffer.get_buffer_size() == 0
    
    async def test_append_audio_data(self):
        """Test appending audio data to buffer."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=1.0)
        
        # Create test audio data (100 samples)
        test_data = np.array([i for i in range(100)], dtype=np.int16)
        audio_bytes = test_data.tobytes()
        
        await buffer.append(audio_bytes)
        
        assert buffer.get_buffer_size() == 100
        assert buffer.get_duration() == pytest.approx(100 / 16000, rel=1e-5)
    
    async def test_append_multiple_chunks(self):
        """Test appending multiple chunks of audio data."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=1.0)
        
        # Append multiple chunks
        for i in range(5):
            test_data = np.array([i] * 100, dtype=np.int16)
            await buffer.append(test_data.tobytes())
        
        assert buffer.get_buffer_size() == 500
    
    async def test_circular_buffer_overflow(self):
        """Test that buffer respects max size (circular behavior)."""
        buffer = AudioBuffer(sample_rate=100, sample_width=2, buffer_duration=1.0)  # Max 100 samples
        
        # Append 150 samples
        test_data = np.array([i for i in range(150)], dtype=np.int16)
        await buffer.append(test_data.tobytes())
        
        # Should only have last 100 samples
        assert buffer.get_buffer_size() == 100
    
    async def test_get_clip_with_sufficient_data(self):
        """Test extracting a clip when buffer has sufficient data."""
        buffer = AudioBuffer(sample_rate=100, sample_width=2, buffer_duration=10.0)
        
        # Add 500 samples (5 seconds of audio at 100 Hz)
        test_data = np.array([i for i in range(500)], dtype=np.int16)
        await buffer.append(test_data.tobytes())
        
        # Get 2-second clip (1s pre + 1s post)
        # Since trigger is at end, we can only get pre_samples
        clip = await buffer.get_clip(pre_duration=1.0, post_duration=1.0)
        
        assert clip is not None
        # Will get 100 pre samples (trigger at end means no post samples available)
        assert len(clip) == 100  # Only pre_samples available when trigger at end
    
    async def test_get_clip_with_insufficient_data(self):
        """Test extracting clip with insufficient buffer data."""
        buffer = AudioBuffer(sample_rate=100, sample_width=2, buffer_duration=10.0)
        
        # Add only 50 samples
        test_data = np.array([i for i in range(50)], dtype=np.int16)
        await buffer.append(test_data.tobytes())
        
        # Try to get 2-second clip (would need 200 samples)
        clip = await buffer.get_clip(pre_duration=1.0, post_duration=1.0)
        
        # Should still return what's available
        assert clip is not None
        assert len(clip) <= 50
    
    async def test_get_clip_empty_buffer(self):
        """Test extracting clip from empty buffer."""
        buffer = AudioBuffer(sample_rate=100, sample_width=2, buffer_duration=10.0)
        
        clip = await buffer.get_clip(pre_duration=1.0, post_duration=1.0)
        
        assert clip is None
    
    async def test_clear_buffer(self):
        """Test clearing the buffer."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=1.0)
        
        # Add some data
        test_data = np.array([i for i in range(100)], dtype=np.int16)
        await buffer.append(test_data.tobytes())
        
        assert buffer.get_buffer_size() == 100
        
        # Clear buffer
        await buffer.clear()
        
        assert buffer.get_buffer_size() == 0
    
    async def test_get_duration(self):
        """Test getting buffer duration in seconds."""
        buffer = AudioBuffer(sample_rate=1000, sample_width=2, buffer_duration=10.0)
        
        # Add 500 samples (0.5 seconds at 1000 Hz)
        test_data = np.array([0] * 500, dtype=np.int16)
        await buffer.append(test_data.tobytes())
        
        assert buffer.get_duration() == pytest.approx(0.5, rel=1e-5)
    
    async def test_sample_width_32bit(self):
        """Test buffer with 32-bit samples."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=4, buffer_duration=1.0)
        
        # Create 32-bit test data
        test_data = np.array([i for i in range(100)], dtype=np.int32)
        audio_bytes = test_data.tobytes()
        
        await buffer.append(audio_bytes)
        
        assert buffer.get_buffer_size() == 100
    
    async def test_concurrent_access(self):
        """Test thread-safe concurrent access to buffer."""
        import asyncio
        
        buffer = AudioBuffer(sample_rate=16000, sample_width=2, buffer_duration=1.0)
        
        async def append_task():
            test_data = np.array([1] * 100, dtype=np.int16)
            await buffer.append(test_data.tobytes())
        
        # Run multiple append tasks concurrently
        await asyncio.gather(*[append_task() for _ in range(10)])
        
        assert buffer.get_buffer_size() == 1000
    
    async def test_little_endian_32bit_decoding(self):
        """Test that 32-bit samples are decoded as little-endian."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=4, channels=1, buffer_duration=1.0)
        
        # Create test data with a known value that differs in big vs little endian
        # Value 0x12345678 in little-endian bytes: 78 56 34 12
        test_value = 0x12345678
        test_data = np.array([test_value], dtype='<i4')  # Explicitly little-endian
        audio_bytes = test_data.tobytes()
        
        await buffer.append(audio_bytes)
        
        # Extract the stored value
        assert buffer.get_buffer_size() == 1
        # The buffer stores individual samples
        assert buffer.buffer[0] == test_value
    
    async def test_little_endian_16bit_decoding(self):
        """Test that 16-bit samples are decoded as little-endian."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=2, channels=1, buffer_duration=1.0)
        
        # Create test data with a known value
        # Value 0x1234 in little-endian bytes: 34 12
        test_value = 0x1234
        test_data = np.array([test_value], dtype='<i2')  # Explicitly little-endian
        audio_bytes = test_data.tobytes()
        
        await buffer.append(audio_bytes)
        
        # Extract the stored value
        assert buffer.get_buffer_size() == 1
        assert buffer.buffer[0] == test_value
    
    async def test_channel_count_validation_mono(self):
        """Test that sample count validation works for mono audio."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=4, channels=1, buffer_duration=1.0)
        
        # Create test data with valid sample count (divisible by 1)
        test_data = np.array([1, 2, 3, 4, 5], dtype='<i4')
        audio_bytes = test_data.tobytes()
        
        # Should succeed
        await buffer.append(audio_bytes)
        assert buffer.get_buffer_size() == 5
    
    async def test_channel_count_validation_stereo_valid(self):
        """Test that sample count validation works for stereo audio with valid data."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=4, channels=2, buffer_duration=1.0)
        
        # Create test data with even sample count (divisible by 2)
        test_data = np.array([1, 2, 3, 4, 5, 6], dtype='<i4')
        audio_bytes = test_data.tobytes()
        
        # Should succeed
        await buffer.append(audio_bytes)
        assert buffer.get_buffer_size() == 6
    
    async def test_channel_count_validation_stereo_invalid(self):
        """Test that sample count validation fails for stereo audio with odd sample count."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=4, channels=2, buffer_duration=1.0)
        
        # Create test data with odd sample count (not divisible by 2)
        test_data = np.array([1, 2, 3, 4, 5], dtype='<i4')
        audio_bytes = test_data.tobytes()
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="Sample count.*not divisible by.*channels"):
            await buffer.append(audio_bytes)
    
    async def test_channel_count_validation_multichannel(self):
        """Test that sample count validation works for multi-channel audio."""
        buffer = AudioBuffer(sample_rate=16000, sample_width=4, channels=4, buffer_duration=1.0)
        
        # Create test data with sample count divisible by 4
        test_data = np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype='<i4')
        audio_bytes = test_data.tobytes()
        
        # Should succeed
        await buffer.append(audio_bytes)
        assert buffer.get_buffer_size() == 8
        
        # Try with invalid count (not divisible by 4)
        test_data_invalid = np.array([1, 2, 3, 4, 5, 6, 7], dtype='<i4')
        audio_bytes_invalid = test_data_invalid.tobytes()
        
        with pytest.raises(ValueError, match="Sample count.*not divisible by.*channels"):
            await buffer.append(audio_bytes_invalid)
