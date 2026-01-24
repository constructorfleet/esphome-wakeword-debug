import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Optional
import numpy as np

from .config import settings

logger = logging.getLogger(__name__)


class AudioBuffer:
    """
    Circular audio buffer that maintains a rolling window of audio data.
    Allows extracting clips around specific events.
    """
    
    def __init__(
        self,
        sample_rate: int = settings.SAMPLE_RATE,
        sample_width: int = settings.SAMPLE_WIDTH,
        channels: int = settings.CHANNELS,
        buffer_duration: float = settings.BUFFER_DURATION_SECONDS
    ):
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.channels = channels
        self.buffer_duration = buffer_duration
        
        # Calculate buffer size in samples
        self.max_samples = int(sample_rate * buffer_duration)
        
        # Use deque for efficient append/pop operations
        self.buffer: deque = deque(maxlen=self.max_samples)
        self.lock = asyncio.Lock()
        
        logger.info(
            f"AudioBuffer initialized: {sample_rate}Hz, "
            f"{sample_width * 8}-bit, {channels} channel(s), "
            f"{buffer_duration}s capacity ({self.max_samples} samples)"
        )
    
    async def append(self, audio_data: bytes) -> None:
        """
        Append raw PCM audio data to the buffer.
        
        Args:
            audio_data: Raw PCM audio bytes
        """
        async with self.lock:
            # Convert bytes to numpy array of samples
            if self.sample_width == 2:
                samples = np.frombuffer(audio_data, dtype=np.int16)
            elif self.sample_width == 4:
                samples = np.frombuffer(audio_data, dtype=np.int32)
            else:
                raise ValueError(f"Unsupported sample width: {self.sample_width}")
            
            # Append each sample to the buffer
            for sample in samples:
                self.buffer.append(sample)
    
    async def get_clip(
        self,
        pre_duration: float = settings.PRE_WAKE_DURATION_SECONDS,
        post_duration: float = settings.POST_WAKE_DURATION_SECONDS,
        trigger_offset: Optional[float] = None
    ) -> Optional[np.ndarray]:
        """
        Extract an audio clip from the buffer around a trigger event.
        
        Args:
            pre_duration: Seconds of audio before the trigger point
            post_duration: Seconds of audio after the trigger point
            trigger_offset: Offset from the current position (None = now)
        
        Returns:
            numpy array of audio samples, or None if insufficient data
        """
        async with self.lock:
            if len(self.buffer) == 0:
                logger.warning("Buffer is empty, cannot extract clip")
                return None
            
            # Calculate sample positions
            pre_samples = int(pre_duration * self.sample_rate)
            post_samples = int(post_duration * self.sample_rate)
            total_samples = pre_samples + post_samples
            
            if trigger_offset is None:
                # Trigger at current position (end of buffer)
                trigger_position = len(self.buffer)
            else:
                # Trigger at specific offset from current position
                offset_samples = int(trigger_offset * self.sample_rate)
                trigger_position = len(self.buffer) - offset_samples
            
            # Calculate clip boundaries
            start_pos = max(0, trigger_position - pre_samples)
            end_pos = min(len(self.buffer), trigger_position + post_samples)
            
            if end_pos - start_pos < total_samples:
                logger.warning(
                    f"Insufficient buffer data for requested clip "
                    f"(have {end_pos - start_pos} samples, need {total_samples})"
                )
            
            # Extract the clip
            clip_samples = []
            for i in range(start_pos, end_pos):
                clip_samples.append(self.buffer[i])
            
            if not clip_samples:
                return None
            
            # Convert to numpy array
            clip = np.array(clip_samples, dtype=np.int16 if self.sample_width == 2 else np.int32)
            
            logger.info(
                f"Extracted clip: {len(clip)} samples "
                f"({len(clip) / self.sample_rate:.2f}s)"
            )
            
            return clip
    
    async def clear(self) -> None:
        """Clear the buffer."""
        async with self.lock:
            self.buffer.clear()
            logger.info("Buffer cleared")
    
    def get_buffer_size(self) -> int:
        """Get current number of samples in buffer."""
        return len(self.buffer)
    
    def get_duration(self) -> float:
        """Get current duration of audio in buffer (seconds)."""
        return len(self.buffer) / self.sample_rate
