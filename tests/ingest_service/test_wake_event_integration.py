"""Integration test to verify wake event captures post-wake audio correctly."""
import pytest
import asyncio
import numpy as np
from ingest_service.app.audio_buffer import MultiAssistantAudioBuffer


@pytest.mark.asyncio
class TestWakeEventIntegration:
    """Integration tests to verify the complete wake event flow."""
    
    async def test_wake_event_captures_post_samples_with_delay(self):
        """
        Test that waiting before extracting clip captures post-wake samples.
        
        This simulates the real-world scenario:
        1. Audio is being buffered continuously
        2. Wake event occurs at time T
        3. System waits POST_WAKE_DURATION_SECONDS
        4. During wait, audio continues to be buffered
        5. After wait, clip is extracted with correct trigger_offset
        """
        # Create buffer with known parameters
        sample_rate = 100  # 100 Hz for easy calculation
        buffer = MultiAssistantAudioBuffer(
            default_sample_rate=sample_rate,
            default_sample_width=2,
            default_channels=1,
            buffer_duration=10.0
        )
        
        # Add initial audio data (5 seconds worth)
        initial_samples = np.array(range(500), dtype=np.int16)
        await buffer.append("test_assistant", initial_samples.tobytes())
        
        # Simulate wake event occurring at this point (after 5 seconds)
        # In real scenario, wake event would trigger at this time
        wake_time = 5.0
        
        # Simulate waiting for post_duration (3 seconds)
        post_duration = 3.0
        
        # During the wait, more audio is captured
        # Simulate 3 more seconds of audio being added
        post_wake_samples = np.array(range(500, 800), dtype=np.int16)
        await buffer.append("test_assistant", post_wake_samples.tobytes())
        
        # Now extract the clip with trigger_offset to indicate wake was 3 seconds ago
        pre_duration = 2.0
        clip = await buffer.get_clip(
            assistant_id="test_assistant",
            pre_duration=pre_duration,
            post_duration=post_duration,
            trigger_offset=post_duration
        )
        
        # Verify the clip was extracted
        assert clip is not None
        
        # Calculate expected samples
        # Wake event was at position 500 (5 seconds)
        # Current position is 800 (8 seconds)
        # trigger_offset=3.0 means trigger was 300 samples ago
        # trigger_position = 800 - 300 = 500 (correct!)
        # pre_duration=2.0 means 200 samples before trigger
        # post_duration=3.0 means 300 samples after trigger
        # Expected: samples 300-800 (500 samples total)
        expected_samples = 500
        
        assert len(clip) == expected_samples, \
            f"Expected {expected_samples} samples but got {len(clip)}"
        
        # Verify the clip contains the correct range of values
        # Should be samples 300-800 (from our test data)
        assert clip[0] == 300, f"First sample should be 300 but got {clip[0]}"
        assert clip[-1] == 799, f"Last sample should be 799 but got {clip[-1]}"
    
    async def test_wake_event_without_delay_misses_post_samples(self):
        """
        Test that extracting clip immediately without delay misses post-wake samples.
        
        This demonstrates the bug that the fix addresses.
        """
        # Create buffer with known parameters
        sample_rate = 100  # 100 Hz for easy calculation
        buffer = MultiAssistantAudioBuffer(
            default_sample_rate=sample_rate,
            default_sample_width=2,
            default_channels=1,
            buffer_duration=10.0
        )
        
        # Add initial audio data (5 seconds worth)
        initial_samples = np.array(range(500), dtype=np.int16)
        await buffer.append("test_assistant", initial_samples.tobytes())
        
        # Simulate wake event occurring at this point
        # WITHOUT waiting, extract clip immediately
        pre_duration = 2.0
        post_duration = 3.0
        
        # Extract clip WITHOUT trigger_offset (simulating old behavior)
        clip = await buffer.get_clip(
            assistant_id="test_assistant",
            pre_duration=pre_duration,
            post_duration=post_duration,
            trigger_offset=None  # No offset = trigger at current position
        )
        
        # Verify the clip was extracted
        assert clip is not None
        
        # Without waiting, we can only get pre_duration samples
        # trigger_position = 500 (end of buffer)
        # pre_samples = 200
        # post_samples = 300 (but buffer only goes to 500!)
        # Result: samples 300-500 (200 samples)
        expected_samples = 200
        
        assert len(clip) == expected_samples, \
            f"Without delay, expected only {expected_samples} samples (pre-wake only) but got {len(clip)}"
        
        # Now simulate what happens when we add post-wake audio AFTER extraction
        # This is too late - the clip was already extracted
        post_wake_samples = np.array(range(500, 800), dtype=np.int16)
        await buffer.append("test_assistant", post_wake_samples.tobytes())
        
        # The previously extracted clip doesn't include these new samples
        assert len(clip) == expected_samples, \
            "Clip should not grow after extraction"
