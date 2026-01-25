import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Optional, Dict, List
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
                samples = np.frombuffer(audio_data, dtype='<i2')  # Little-endian 16-bit signed int
            elif self.sample_width == 4:
                samples = np.frombuffer(audio_data, dtype='<i4')  # Little-endian 32-bit signed int
            else:
                raise ValueError(f"Unsupported sample width: {self.sample_width}")
            
            # Verify sample count is divisible by number of channels
            if len(samples) % self.channels != 0:
                raise ValueError(
                    f"Sample count ({len(samples)}) is not divisible by "
                    f"number of channels ({self.channels})"
                )
            
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


class MultiAssistantAudioBuffer:
    """
    Manages multiple AudioBuffer instances, one per assistant ID.
    Each assistant can have its own audio configuration.
    """
    
    def __init__(
        self,
        default_sample_rate: int = settings.SAMPLE_RATE,
        default_sample_width: int = settings.SAMPLE_WIDTH,
        default_channels: int = settings.CHANNELS,
        buffer_duration: float = settings.BUFFER_DURATION_SECONDS
    ):
        self.default_sample_rate = default_sample_rate
        self.default_sample_width = default_sample_width
        self.default_channels = default_channels
        self.buffer_duration = buffer_duration
        
        # Dictionary to hold buffers per assistant ID
        self.buffers: Dict[str, AudioBuffer] = {}
        # Dictionary to hold per-assistant audio configuration
        self.assistant_configs: Dict[str, dict] = {}
        self.lock = asyncio.Lock()
        
        logger.info(
            f"MultiAssistantAudioBuffer initialized with defaults: {default_sample_rate}Hz, "
            f"{default_sample_width * 8}-bit, {default_channels} channel(s), "
            f"{buffer_duration}s capacity per assistant"
        )
    
    async def set_audio_config(self, assistant_id: str, sample_rate: int, bits_per_sample: int, channels: int) -> None:
        """
        Set audio configuration for a specific assistant.
        If a buffer already exists, it will be recreated with the new configuration.
        
        Args:
            assistant_id: Unique identifier for the assistant
            sample_rate: Sample rate in Hz
            bits_per_sample: Bits per sample (e.g., 16, 32)
            channels: Number of audio channels
        """
        async with self.lock:
            sample_width = bits_per_sample // 8  # Convert bits to bytes
            
            config = {
                "sample_rate": sample_rate,
                "sample_width": sample_width,
                "channels": channels
            }
            
            self.assistant_configs[assistant_id] = config
            
            # Recreate buffer with new configuration
            logger.info(
                f"Setting audio config for assistant {assistant_id}: "
                f"{sample_rate}Hz, {bits_per_sample}-bit, {channels} channel(s)"
            )
            
            self.buffers[assistant_id] = AudioBuffer(
                sample_rate=sample_rate,
                sample_width=sample_width,
                channels=channels,
                buffer_duration=self.buffer_duration
            )
    
    async def get_buffer(self, assistant_id: str) -> AudioBuffer:
        """
        Get or create a buffer for a specific assistant ID.
        Uses assistant-specific config if available, otherwise uses defaults.
        
        Args:
            assistant_id: Unique identifier for the assistant
        
        Returns:
            AudioBuffer instance for the assistant
        """
        async with self.lock:
            if assistant_id not in self.buffers:
                # Use assistant-specific config if available, otherwise use defaults
                config = self.assistant_configs.get(assistant_id, {})
                sample_rate = config.get("sample_rate", self.default_sample_rate)
                sample_width = config.get("sample_width", self.default_sample_width)
                channels = config.get("channels", self.default_channels)
                
                logger.info(
                    f"Creating new buffer for assistant {assistant_id}: "
                    f"{sample_rate}Hz, {sample_width * 8}-bit, {channels} channel(s)"
                )
                
                self.buffers[assistant_id] = AudioBuffer(
                    sample_rate=sample_rate,
                    sample_width=sample_width,
                    channels=channels,
                    buffer_duration=self.buffer_duration
                )
            return self.buffers[assistant_id]
    
    async def append(self, assistant_id: str, audio_data: bytes) -> None:
        """
        Append audio data to a specific assistant's buffer.
        
        Args:
            assistant_id: Unique identifier for the assistant
            audio_data: Raw PCM audio bytes
        """
        buffer = await self.get_buffer(assistant_id)
        await buffer.append(audio_data)
    
    async def get_clip(
        self,
        assistant_id: str,
        pre_duration: float = settings.PRE_WAKE_DURATION_SECONDS,
        post_duration: float = settings.POST_WAKE_DURATION_SECONDS,
        trigger_offset: Optional[float] = None
    ) -> Optional[np.ndarray]:
        """
        Extract a clip from a specific assistant's buffer.
        
        Args:
            assistant_id: Unique identifier for the assistant
            pre_duration: Seconds of audio before the trigger point
            post_duration: Seconds of audio after the trigger point
            trigger_offset: Offset from the current position (None = now)
        
        Returns:
            numpy array of audio samples, or None if insufficient data
        """
        buffer = await self.get_buffer(assistant_id)
        return await buffer.get_clip(pre_duration, post_duration, trigger_offset)
    
    async def clear(self, assistant_id: Optional[str] = None) -> None:
        """
        Clear buffer(s).
        
        Args:
            assistant_id: Specific assistant to clear, or None to clear all
        """
        async with self.lock:
            if assistant_id is None:
                # Clear all buffers
                for buffer in self.buffers.values():
                    await buffer.clear()
                logger.info("All assistant buffers cleared")
            elif assistant_id in self.buffers:
                await self.buffers[assistant_id].clear()
    
    def get_buffer_size(self, assistant_id: Optional[str] = None) -> int:
        """Get total number of samples across all assistants or for specific assistant."""
        if assistant_id and assistant_id in self.buffers:
            return self.buffers[assistant_id].get_buffer_size()
        return sum(buffer.get_buffer_size() for buffer in self.buffers.values())
    
    def get_duration(self, assistant_id: Optional[str] = None) -> float:
        """Get total duration across all assistants or for specific assistant."""
        if assistant_id and assistant_id in self.buffers:
            return self.buffers[assistant_id].get_duration()
        # Return average duration across all buffers
        if not self.buffers:
            return 0.0
        return sum(buffer.get_duration() for buffer in self.buffers.values()) / len(self.buffers)
    
    def get_assistant_ids(self) -> List[str]:
        """Get list of all assistant IDs with active buffers."""
        return list(self.buffers.keys())
