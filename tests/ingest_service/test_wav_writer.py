"""Unit tests for WAVWriter class."""
import pytest
import wave
import numpy as np
from pathlib import Path
from ingest_service.app.wav_writer import WAVWriter


class TestWAVWriter:
    """Test cases for WAVWriter."""
    
    def test_init_creates_output_dir(self, tmp_path):
        """Test that WAVWriter creates output directory if it doesn't exist."""
        output_dir = tmp_path / "audio_output"
        writer = WAVWriter(output_dir=str(output_dir))
        
        assert output_dir.exists()
        assert output_dir.is_dir()
    
    def test_write_clip_default_filename(self, tmp_path):
        """Test writing clip with auto-generated filename."""
        writer = WAVWriter(output_dir=str(tmp_path))
        
        # Create test audio data
        test_data = np.array([i for i in range(1000)], dtype=np.int16)
        
        wav_path = writer.write_clip(test_data)
        
        assert Path(wav_path).exists()
        assert Path(wav_path).suffix == ".wav"
        assert "wake_event_" in Path(wav_path).name
    
    def test_write_clip_custom_filename(self, tmp_path):
        """Test writing clip with custom filename."""
        writer = WAVWriter(output_dir=str(tmp_path))
        
        test_data = np.array([i for i in range(1000)], dtype=np.int16)
        custom_name = "test_audio.wav"
        
        wav_path = writer.write_clip(test_data, filename=custom_name)
        
        assert Path(wav_path).exists()
        assert Path(wav_path).name == custom_name
    
    def test_write_clip_correct_format(self, tmp_path):
        """Test that written WAV file has correct format."""
        sample_rate = 16000
        sample_width = 2
        channels = 1
        
        writer = WAVWriter(
            output_dir=str(tmp_path),
            sample_rate=sample_rate,
            sample_width=sample_width,
            channels=channels
        )
        
        test_data = np.array([i for i in range(1000)], dtype=np.int16)
        wav_path = writer.write_clip(test_data)
        
        # Read back and verify
        with wave.open(wav_path, 'rb') as wav_file:
            assert wav_file.getnchannels() == channels
            assert wav_file.getsampwidth() == sample_width
            assert wav_file.getframerate() == sample_rate
            assert wav_file.getnframes() == len(test_data)
    
    def test_write_clip_with_metadata(self, tmp_path):
        """Test writing clip with metadata."""
        writer = WAVWriter(output_dir=str(tmp_path))
        
        test_data = np.array([i for i in range(1000)], dtype=np.int16)
        metadata = {
            "timestamp": "2024-01-01T00:00:00",
            "duration": 0.0625,
            "sample_rate": 16000
        }
        
        wav_path = writer.write_clip(test_data, filename="test.wav", metadata=metadata)
        
        # Check that metadata file exists
        metadata_path = Path(wav_path).with_suffix('.json')
        assert metadata_path.exists()
        
        # Verify metadata content
        import json
        with open(metadata_path, 'r') as f:
            loaded_metadata = json.load(f)
        
        assert loaded_metadata == metadata
    
    def test_write_clip_data_integrity(self, tmp_path):
        """Test that written data matches input data."""
        writer = WAVWriter(output_dir=str(tmp_path), sample_rate=16000)
        
        # Create known test data
        test_data = np.array([100, 200, 300, 400, 500], dtype=np.int16)
        wav_path = writer.write_clip(test_data)
        
        # Read back and compare
        with wave.open(wav_path, 'rb') as wav_file:
            frames = wav_file.readframes(len(test_data))
            read_data = np.frombuffer(frames, dtype=np.int16)
        
        np.testing.assert_array_equal(read_data, test_data)
    
    def test_cleanup_old_files(self, tmp_path):
        """Test cleanup of old WAV files."""
        import time
        
        writer = WAVWriter(output_dir=str(tmp_path))
        
        # Create some test files
        test_data = np.array([i for i in range(100)], dtype=np.int16)
        
        # Create old file
        old_file = tmp_path / "old_file.wav"
        writer.write_clip(test_data, filename=old_file.name)
        
        # Modify timestamp to make it old (8 days ago)
        old_time = time.time() - (8 * 86400)
        old_file.touch()
        import os
        os.utime(old_file, (old_time, old_time))
        
        # Create recent file
        recent_file = tmp_path / "recent_file.wav"
        writer.write_clip(test_data, filename=recent_file.name)
        
        # Cleanup files older than 7 days
        deleted_count = writer.cleanup_old_files(max_age_days=7)
        
        assert deleted_count == 1
        assert not old_file.exists()
        assert recent_file.exists()
    
    def test_cleanup_with_metadata_files(self, tmp_path):
        """Test that cleanup also removes companion metadata files."""
        import time
        
        writer = WAVWriter(output_dir=str(tmp_path))
        
        test_data = np.array([i for i in range(100)], dtype=np.int16)
        metadata = {"test": "data"}
        
        # Create old file with metadata
        old_file_path = writer.write_clip(
            test_data,
            filename="old_file.wav",
            metadata=metadata
        )
        
        old_file = Path(old_file_path)
        metadata_file = old_file.with_suffix('.json')
        
        # Make files old
        old_time = time.time() - (8 * 86400)
        import os
        os.utime(old_file, (old_time, old_time))
        
        assert metadata_file.exists()
        
        # Cleanup
        writer.cleanup_old_files(max_age_days=7)
        
        assert not old_file.exists()
        assert not metadata_file.exists()
    
    def test_write_clip_with_different_sample_widths(self, tmp_path):
        """Test writing clips with different sample widths."""
        # Test 16-bit
        writer_16 = WAVWriter(output_dir=str(tmp_path), sample_width=2)
        data_16 = np.array([100, 200, 300], dtype=np.int16)
        wav_path_16 = writer_16.write_clip(data_16, filename="test_16bit.wav")
        
        with wave.open(wav_path_16, 'rb') as f:
            assert f.getsampwidth() == 2
        
        # Test 32-bit
        writer_32 = WAVWriter(output_dir=str(tmp_path), sample_width=4)
        data_32 = np.array([100, 200, 300], dtype=np.int32)
        wav_path_32 = writer_32.write_clip(data_32, filename="test_32bit.wav")
        
        with wave.open(wav_path_32, 'rb') as f:
            assert f.getsampwidth() == 4
    
    def test_write_clip_with_custom_audio_params(self, tmp_path):
        """Test writing clip with custom audio parameters that override instance defaults."""
        # Create writer with default settings
        writer = WAVWriter(
            output_dir=str(tmp_path),
            sample_rate=16000,
            sample_width=2,
            channels=1
        )
        
        # Write clip with different parameters (simulating MQTT config)
        test_data = np.array([i for i in range(1000)], dtype=np.int32)
        wav_path = writer.write_clip(
            test_data,
            filename="custom_config.wav",
            sample_rate=48000,
            sample_width=4,
            channels=2
        )
        
        # Verify the WAV file uses custom parameters, not defaults
        with wave.open(wav_path, 'rb') as wav_file:
            assert wav_file.getframerate() == 48000  # Custom, not 16000
            assert wav_file.getsampwidth() == 4  # Custom, not 2
            assert wav_file.getnchannels() == 2  # Custom, not 1
    
    def test_write_clip_falls_back_to_defaults(self, tmp_path):
        """Test that write_clip uses instance defaults when custom params not provided."""
        writer = WAVWriter(
            output_dir=str(tmp_path),
            sample_rate=24000,
            sample_width=2,
            channels=2
        )
        
        test_data = np.array([i for i in range(1000)], dtype=np.int16)
        wav_path = writer.write_clip(test_data, filename="default_config.wav")
        
        # Verify the WAV file uses instance defaults
        with wave.open(wav_path, 'rb') as wav_file:
            assert wav_file.getframerate() == 24000
            assert wav_file.getsampwidth() == 2
            assert wav_file.getnchannels() == 2
