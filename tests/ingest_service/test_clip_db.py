"""Tests for clip_db module."""
import tempfile
from pathlib import Path
import pytest

from ingest_service.app import clip_db


@pytest.fixture
def temp_db_path():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


def test_init_db(temp_db_path):
    """Test database initialization."""
    clip_db.init_db(temp_db_path)
    assert temp_db_path.exists()


def test_insert_clip(temp_db_path):
    """Test inserting a clip."""
    clip_db.init_db(temp_db_path)
    
    clip_id = clip_db.insert_clip(
        temp_db_path,
        filename="test.wav",
        timestamp="2024-01-01T00:00:00Z",
        assistant_id="test_assistant",
        duration=5.0,
        sample_rate=48000,
        label=clip_db.LABEL_UNKNOWN,
    )
    
    assert clip_id > 0
    
    # Verify the clip was inserted
    row = clip_db.get_clip(temp_db_path, clip_id)
    assert row is not None
    assert row["filename"] == "test.wav"
    assert row["label"] == clip_db.LABEL_UNKNOWN


def test_new_labels(temp_db_path):
    """Test new label types."""
    clip_db.init_db(temp_db_path)
    
    # Test False Negative label
    clip_id1 = clip_db.insert_clip(
        temp_db_path,
        filename="false_negative.wav",
        timestamp="2024-01-01T00:00:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
        label=clip_db.LABEL_FALSE_NEGATIVE,
    )
    
    row1 = clip_db.get_clip(temp_db_path, clip_id1)
    assert row1["label"] == clip_db.LABEL_FALSE_NEGATIVE
    
    # Test Background Noise label
    clip_id2 = clip_db.insert_clip(
        temp_db_path,
        filename="background_noise.wav",
        timestamp="2024-01-01T00:01:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
        label=clip_db.LABEL_BACKGROUND_NOISE,
    )
    
    row2 = clip_db.get_clip(temp_db_path, clip_id2)
    assert row2["label"] == clip_db.LABEL_BACKGROUND_NOISE


def test_update_label(temp_db_path):
    """Test updating a clip's label."""
    clip_db.init_db(temp_db_path)
    
    clip_id = clip_db.insert_clip(
        temp_db_path,
        filename="test.wav",
        timestamp="2024-01-01T00:00:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
        label=clip_db.LABEL_UNKNOWN,
    )
    
    # Update to False Negative
    success = clip_db.update_label(temp_db_path, clip_id, clip_db.LABEL_FALSE_NEGATIVE)
    assert success
    
    row = clip_db.get_clip(temp_db_path, clip_id)
    assert row["label"] == clip_db.LABEL_FALSE_NEGATIVE
    
    # Update to Background Noise
    success = clip_db.update_label(temp_db_path, clip_id, clip_db.LABEL_BACKGROUND_NOISE)
    assert success
    
    row = clip_db.get_clip(temp_db_path, clip_id)
    assert row["label"] == clip_db.LABEL_BACKGROUND_NOISE


def test_soft_delete(temp_db_path):
    """Test soft-deleting a clip."""
    clip_db.init_db(temp_db_path)
    
    clip_id = clip_db.insert_clip(
        temp_db_path,
        filename="test.wav",
        timestamp="2024-01-01T00:00:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
    )
    
    # Verify clip is not deleted
    row = clip_db.get_clip(temp_db_path, clip_id)
    assert row["deleted"] == 0
    
    # Soft delete the clip
    success = clip_db.soft_delete_clip(temp_db_path, clip_id)
    assert success
    
    # Verify clip is marked as deleted
    row = clip_db.get_clip(temp_db_path, clip_id)
    assert row["deleted"] == 1


def test_undelete(temp_db_path):
    """Test restoring a soft-deleted clip."""
    clip_db.init_db(temp_db_path)
    
    clip_id = clip_db.insert_clip(
        temp_db_path,
        filename="test.wav",
        timestamp="2024-01-01T00:00:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
    )
    
    # Soft delete the clip
    clip_db.soft_delete_clip(temp_db_path, clip_id)
    
    # Restore the clip
    success = clip_db.undelete_clip(temp_db_path, clip_id)
    assert success
    
    # Verify clip is no longer deleted
    row = clip_db.get_clip(temp_db_path, clip_id)
    assert row["deleted"] == 0


def test_list_clips_exclude_deleted(temp_db_path):
    """Test that deleted clips are excluded by default."""
    clip_db.init_db(temp_db_path)
    
    # Insert a regular clip
    clip_id1 = clip_db.insert_clip(
        temp_db_path,
        filename="test1.wav",
        timestamp="2024-01-01T00:00:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
    )
    
    # Insert and delete another clip
    clip_id2 = clip_db.insert_clip(
        temp_db_path,
        filename="test2.wav",
        timestamp="2024-01-01T00:01:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
    )
    clip_db.soft_delete_clip(temp_db_path, clip_id2)
    
    # List clips without including deleted
    clips = clip_db.list_clips(temp_db_path, include_deleted=False)
    assert len(clips) == 1
    assert clips[0]["id"] == clip_id1


def test_list_clips_include_deleted(temp_db_path):
    """Test that deleted clips can be included."""
    clip_db.init_db(temp_db_path)
    
    # Insert a regular clip
    clip_id1 = clip_db.insert_clip(
        temp_db_path,
        filename="test1.wav",
        timestamp="2024-01-01T00:00:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
    )
    
    # Insert and delete another clip
    clip_id2 = clip_db.insert_clip(
        temp_db_path,
        filename="test2.wav",
        timestamp="2024-01-01T00:01:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
    )
    clip_db.soft_delete_clip(temp_db_path, clip_id2)
    
    # List clips including deleted
    clips = clip_db.list_clips(temp_db_path, include_deleted=True)
    assert len(clips) == 2
    returned_ids = {clip["id"] for clip in clips}
    assert returned_ids == {clip_id1, clip_id2}


def test_list_clips_filter_by_label(temp_db_path):
    """Test filtering clips by label."""
    clip_db.init_db(temp_db_path)
    
    # Insert clips with different labels
    clip_db.insert_clip(
        temp_db_path,
        filename="positive.wav",
        timestamp="2024-01-01T00:00:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
        label=clip_db.LABEL_POSITIVE,
    )
    
    clip_db.insert_clip(
        temp_db_path,
        filename="false_negative.wav",
        timestamp="2024-01-01T00:01:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
        label=clip_db.LABEL_FALSE_NEGATIVE,
    )
    
    clip_db.insert_clip(
        temp_db_path,
        filename="background_noise.wav",
        timestamp="2024-01-01T00:02:00Z",
        assistant_id="test",
        duration=5.0,
        sample_rate=48000,
        label=clip_db.LABEL_BACKGROUND_NOISE,
    )
    
    # Filter by False Negative
    clips = clip_db.list_clips(temp_db_path, label=clip_db.LABEL_FALSE_NEGATIVE)
    assert len(clips) == 1
    assert clips[0]["label"] == clip_db.LABEL_FALSE_NEGATIVE
    
    # Filter by Background Noise
    clips = clip_db.list_clips(temp_db_path, label=clip_db.LABEL_BACKGROUND_NOISE)
    assert len(clips) == 1
    assert clips[0]["label"] == clip_db.LABEL_BACKGROUND_NOISE
