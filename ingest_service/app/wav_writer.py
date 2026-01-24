import os
import wave
import logging
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import numpy as np

from .config import settings

logger = logging.getLogger(__name__)


class WAVWriter:
    """Handles writing audio clips to WAV files."""
    
    def __init__(
        self,
        output_dir: str = settings.OUTPUT_DIR,
        sample_rate: int = settings.SAMPLE_RATE,
        sample_width: int = settings.SAMPLE_WIDTH,
        channels: int = settings.CHANNELS
    ):
        self.output_dir = Path(output_dir)
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.channels = channels
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"WAVWriter initialized: output_dir={self.output_dir}")
    
    def write_clip(
        self,
        audio_data: np.ndarray,
        filename: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> str:
        """
        Write audio data to a WAV file.
        
        Args:
            audio_data: numpy array of audio samples
            filename: Optional filename (generated if not provided)
            metadata: Optional metadata dictionary
        
        Returns:
            Path to the written file
        """
        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"wake_event_{timestamp}.wav"
        
        filepath = self.output_dir / filename
        
        try:
            with wave.open(str(filepath), 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(self.sample_width)
                wav_file.setframerate(self.sample_rate)
                
                # Convert numpy array to bytes
                audio_bytes = audio_data.tobytes()
                wav_file.writeframes(audio_bytes)
            
            file_size = filepath.stat().st_size
            duration = len(audio_data) / self.sample_rate
            
            logger.info(
                f"Wrote WAV file: {filepath.name} "
                f"(size={file_size} bytes, duration={duration:.2f}s)"
            )
            
            # Write metadata if provided
            if metadata:
                self._write_metadata(filepath, metadata)
            
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Failed to write WAV file {filepath}: {e}")
            raise
    
    def _write_metadata(self, wav_path: Path, metadata: dict) -> None:
        """
        Write metadata to a companion JSON file.
        
        Args:
            wav_path: Path to the WAV file
            metadata: Metadata dictionary
        """
        metadata_path = wav_path.with_suffix('.json')
        
        try:
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.debug(f"Wrote metadata: {metadata_path.name}")
        except Exception as e:
            logger.warning(f"Failed to write metadata {metadata_path}: {e}")
    
    def cleanup_old_files(self, max_age_days: int = 7) -> int:
        """
        Remove WAV files older than specified days.
        
        Args:
            max_age_days: Maximum age of files to keep
        
        Returns:
            Number of files deleted
        """
        deleted_count = 0
        current_time = time.time()
        max_age_seconds = max_age_days * 86400
        
        try:
            for filepath in self.output_dir.glob("*.wav"):
                file_age = current_time - filepath.stat().st_mtime
                if file_age > max_age_seconds:
                    # Also remove companion metadata file if exists
                    metadata_path = filepath.with_suffix('.json')
                    if metadata_path.exists():
                        metadata_path.unlink()
                    
                    filepath.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old file: {filepath.name}")
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old audio files")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return deleted_count
