import asyncio
import json
import logging
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Path as FastAPIPath,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from .config import settings
from .audio_buffer import MultiAssistantAudioBuffer
from .wav_writer import WAVWriter
from .mqtt_publisher import MQTTPublisher
from .mqtt_subscriber import MQTTSubscriber
from . import clip_db

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Wake Word Audio Ingest Service",
    description="Receives audio streams, buffers, and saves wake word clips",
    version="1.0.0",
)

# UI and clip storage paths
CLIP_BASE_DIR = Path(os.getenv("OUTPUT_DIR", settings.OUTPUT_DIR)).resolve()
CLIP_DB_PATH = Path(
    os.getenv("CLIP_DB_PATH", str(CLIP_BASE_DIR / "clips.db"))
).resolve()
STATIC_DIR = Path(__file__).parent / "static"
CLIP_LABELS = {
    clip_db.LABEL_POSITIVE,
    clip_db.LABEL_FALSE_POSITIVE,
    clip_db.LABEL_FALSE_NEGATIVE,
    clip_db.LABEL_BACKGROUND_NOISE,
    clip_db.LABEL_UNKNOWN,
}

# Serve the review UI
if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

# Initialize components (lazy initialization)
audio_buffer: Optional[MultiAssistantAudioBuffer] = None
wav_writer: Optional[WAVWriter] = None
mqtt_publisher: Optional[MQTTPublisher] = None
mqtt_subscriber: Optional[MQTTSubscriber] = None

# Track active websocket connections
active_connections: list[WebSocket] = []

# Store reference to main event loop for thread-safe task scheduling.
# MQTT callbacks run in a separate thread and need to schedule coroutines
# on the main event loop using asyncio.run_coroutine_threadsafe().
main_event_loop: Optional[asyncio.AbstractEventLoop] = None


class ClipLabelRequest(BaseModel):
    label: str


class CaptureBackgroundNoiseRequest(BaseModel):
    seconds: float
    assistant_id: str = "default"


def get_audio_buffer() -> MultiAssistantAudioBuffer:
    """Get or create audio buffer instance."""
    global audio_buffer
    if audio_buffer is None:
        audio_buffer = MultiAssistantAudioBuffer()
    return audio_buffer


def get_wav_writer() -> WAVWriter:
    """Get or create WAV writer instance."""
    global wav_writer
    if wav_writer is None:
        wav_writer = WAVWriter()
    return wav_writer


def get_mqtt_publisher() -> MQTTPublisher:
    """Get or create MQTT publisher instance."""
    global mqtt_publisher
    if mqtt_publisher is None:
        mqtt_publisher = MQTTPublisher()
    return mqtt_publisher


def get_mqtt_subscriber() -> MQTTSubscriber:
    """Get or create MQTT subscriber instance."""
    global mqtt_subscriber
    if mqtt_subscriber is None:
        mqtt_subscriber = MQTTSubscriber()
    return mqtt_subscriber


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid datetime: {value}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clip_metadata(wav_path: Path) -> dict:
    metadata_path = wav_path.with_suffix(".json")
    if metadata_path.exists():
        try:
            with open(metadata_path, "r") as metadata_file:
                return json.load(metadata_file)
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to read metadata for %s", wav_path.name)
    return {}


def _clip_timestamp(metadata: dict, wav_path: Path) -> datetime:
    timestamp = metadata.get("timestamp")
    if isinstance(timestamp, str):
        try:
            return _parse_datetime(timestamp)
        except HTTPException:
            pass
    return datetime.fromtimestamp(wav_path.stat().st_mtime, tz=timezone.utc)


def _clip_path_from_filename(filename: str) -> Path:
    candidate = (CLIP_BASE_DIR / filename).resolve()
    try:
        candidate.relative_to(CLIP_BASE_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid clip path") from exc
    if candidate.suffix.lower() != ".wav":
        raise HTTPException(status_code=400, detail="Invalid clip path")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Clip not found")
    return candidate


def _sync_clips_from_disk() -> None:
    if not CLIP_BASE_DIR.exists():
        return
    for wav_path in CLIP_BASE_DIR.glob("*.wav"):
        metadata = _clip_metadata(wav_path)
        timestamp = _clip_timestamp(metadata, wav_path)
        clip_db.insert_clip(
            CLIP_DB_PATH,
            filename=wav_path.name,
            timestamp=timestamp.isoformat().replace("+00:00", "Z"),
            assistant_id=metadata.get("assistant_id"),
            duration=metadata.get("duration"),
            sample_rate=metadata.get("sample_rate"),
            label=clip_db.LABEL_UNKNOWN,
        )


async def handle_audio_data(assistant_id: str, audio_data: bytes) -> None:
    """Handle incoming audio data from MQTT."""
    buffer = get_audio_buffer()
    await buffer.append(assistant_id, audio_data)
    logger.debug(
        f"Received {len(audio_data)} bytes of audio data for assistant {assistant_id}"
    )


async def handle_audio_info(assistant_id: str, audio_info: dict) -> None:
    """Handle audio info configuration from MQTT."""
    logger.info(f"Configuring audio for assistant {assistant_id}: {audio_info}")

    try:
        buffer = get_audio_buffer()

        # Extract audio parameters
        sample_rate = audio_info.get("sample_rate")
        bits_per_sample = audio_info.get("bits_per_sample")
        channels = audio_info.get("channels")

        # Validate required fields
        if not all([sample_rate, bits_per_sample, channels]):
            logger.error(
                f"Invalid audio info for assistant {assistant_id}: "
                f"missing required fields (sample_rate, bits_per_sample, channels)"
            )
            return

        # Set audio configuration for this assistant
        await buffer.set_audio_config(
            assistant_id, sample_rate, bits_per_sample, channels
        )

        logger.info(
            f"Audio configuration set for assistant {assistant_id}: "
            f"{sample_rate}Hz, {bits_per_sample}-bit, {channels} channel(s)"
        )

    except Exception as e:
        logger.error(f"Error processing audio info for assistant {assistant_id}: {e}")


async def handle_wake_event(assistant_id: str, metadata: dict) -> None:
    """Handle wake word event from MQTT."""
    logger.info(f"Wake word detected for assistant {assistant_id}: {metadata}")

    # Check if this is a wake event
    if metadata.get("event") != "wake":
        return

    try:
        buffer = get_audio_buffer()
        writer = get_wav_writer()
        mqtt = get_mqtt_publisher()

        # Use default durations for wake event
        pre_duration = settings.PRE_WAKE_DURATION_SECONDS
        post_duration = settings.POST_WAKE_DURATION_SECONDS

        # Wait for POST_WAKE_DURATION_SECONDS to capture audio after wake event
        logger.info(
            f"Waiting {post_duration}s to capture post-wake audio for assistant {assistant_id}"
        )
        await asyncio.sleep(post_duration)

        # Extract clip from buffer for this assistant
        # Use trigger_offset to indicate the wake event was post_duration seconds ago
        clip = await buffer.get_clip(
            assistant_id=assistant_id,
            pre_duration=pre_duration,
            post_duration=post_duration,
            trigger_offset=post_duration,
        )

        if clip is None:
            logger.warning(
                f"Insufficient audio data in buffer for assistant {assistant_id}"
            )
            return

        # Get audio configuration for this assistant (MQTT config takes precedence over ENV)
        audio_config = buffer.get_audio_config(assistant_id)
        sample_rate = audio_config["sample_rate"]
        sample_width = audio_config["sample_width"]
        channels = audio_config["channels"]

        # Create metadata
        timestamp = datetime.utcnow().isoformat()
        clip_metadata = {
            "timestamp": timestamp,
            "assistant_id": assistant_id,
            "pre_duration": pre_duration,
            "post_duration": post_duration,
            "sample_rate": sample_rate,
            "samples": len(clip),
            "duration": len(clip) / (sample_rate * channels),
            "wake_metadata": metadata,
        }

        # Write WAV file with assistant-specific audio configuration
        wav_path = writer.write_clip(
            clip,
            metadata=clip_metadata,
            sample_rate=sample_rate,
            sample_width=sample_width,
            channels=channels,
        )

        clip_db.insert_clip(
            CLIP_DB_PATH,
            filename=Path(wav_path).name,
            timestamp=timestamp.replace("+00:00", "Z"),
            assistant_id=assistant_id,
            duration=clip_metadata.get("duration"),
            sample_rate=sample_rate,
            label=clip_db.LABEL_UNKNOWN,
        )

        # Publish MQTT event
        mqtt.publish_wake_event(wav_path, clip_metadata)

        logger.info(f"Wake event processed for assistant {assistant_id}: {wav_path}")

    except Exception as e:
        logger.error(
            f"Error processing wake event from MQTT for assistant {assistant_id}: {e}"
        )


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global main_event_loop

    # Store reference to the main event loop
    main_event_loop = asyncio.get_running_loop()

    logger.info("Starting Wake Word Audio Ingest Service...")
    logger.info(f"Server: {settings.HOST}:{settings.PORT}")
    logger.info(f"Sample Rate: {settings.SAMPLE_RATE} Hz")
    logger.info(f"Buffer Duration: {settings.BUFFER_DURATION_SECONDS}s")
    logger.info(f"Output Directory: {settings.OUTPUT_DIR}")
    logger.info(f"Clip DB Path: {CLIP_DB_PATH}")

    # Initialize components
    get_audio_buffer()
    get_wav_writer()
    clip_db.init_db(CLIP_DB_PATH)
    _sync_clips_from_disk()

    # Connect to MQTT broker (publisher)
    mqtt = get_mqtt_publisher()
    if mqtt.connect():
        logger.info("MQTT publisher connection established")
    else:
        logger.warning("Failed to connect MQTT publisher to broker")

    # Connect to MQTT broker (subscriber)
    subscriber = get_mqtt_subscriber()

    # Set up callbacks with thread-safe asyncio wrappers
    def audio_callback(assistant_id: str, data: bytes):
        """Thread-safe wrapper for async audio handler."""
        if main_event_loop and not main_event_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                handle_audio_data(assistant_id, data), main_event_loop
            )

    def audio_info_callback(assistant_id: str, audio_info: dict):
        """Thread-safe wrapper for async audio info handler."""
        if main_event_loop and not main_event_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                handle_audio_info(assistant_id, audio_info), main_event_loop
            )

    def wake_callback(assistant_id: str, metadata: dict):
        """Thread-safe wrapper for async wake handler."""
        if main_event_loop and not main_event_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                handle_wake_event(assistant_id, metadata), main_event_loop
            )

    subscriber.set_audio_callback(audio_callback)
    subscriber.set_audio_info_callback(audio_info_callback)
    subscriber.set_wake_callback(wake_callback)

    if subscriber.connect():
        logger.info("MQTT subscriber connection established")
    else:
        logger.warning("Failed to connect MQTT subscriber to broker")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down Wake Word Audio Ingest Service...")

    mqtt = get_mqtt_publisher()
    mqtt.disconnect()

    subscriber = get_mqtt_subscriber()
    subscriber.disconnect()


@app.get("/")
async def root():
    """Root endpoint with service information."""
    buffer = get_audio_buffer()
    return {
        "service": "Wake Word Audio Ingest Service",
        "version": "1.0.0",
        "status": "running",
        "buffer_duration": buffer.get_duration(),
        "active_connections": len(active_connections),
        "active_assistants": buffer.get_assistant_ids(),
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    buffer = get_audio_buffer()
    mqtt = get_mqtt_publisher()
    subscriber = get_mqtt_subscriber()
    return {
        "status": "healthy",
        "mqtt_publisher_connected": mqtt.connected,
        "mqtt_subscriber_connected": subscriber.connected,
        "buffer_samples": buffer.get_buffer_size(),
        "buffer_duration_seconds": buffer.get_duration(),
        "active_assistants": buffer.get_assistant_ids(),
    }


@app.get("/api/assistants")
async def get_assistants():
    """Get list of active assistant IDs."""
    buffer = get_audio_buffer()
    assistant_ids = buffer.get_assistant_ids()
    return {"assistants": assistant_ids if assistant_ids else ["default"]}


@app.post("/wake_event")
async def trigger_wake_event(
    assistant_id: str = "default",
    pre_duration: float = settings.PRE_WAKE_DURATION_SECONDS,
    post_duration: float = settings.POST_WAKE_DURATION_SECONDS,
):
    """
    Manually trigger a wake event to capture and save an audio clip.

    Args:
        assistant_id: Assistant ID to capture audio from
        pre_duration: Seconds of audio before the event
        post_duration: Seconds of audio after the event

    Returns:
        Information about the saved clip
    """
    try:
        buffer = get_audio_buffer()
        writer = get_wav_writer()
        mqtt = get_mqtt_publisher()

        # Wait for POST_WAKE_DURATION_SECONDS to capture audio after wake event
        logger.info(
            f"Waiting {post_duration}s to capture post-wake audio for assistant {assistant_id}"
        )
        await asyncio.sleep(post_duration)

        # Extract clip from buffer for this assistant
        # Use trigger_offset to indicate the wake event was post_duration seconds ago
        clip = await buffer.get_clip(
            assistant_id=assistant_id,
            pre_duration=pre_duration,
            post_duration=post_duration,
            trigger_offset=post_duration,
        )

        if clip is None:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient audio data in buffer for assistant {assistant_id}",
            )

        # Get audio configuration for this assistant (MQTT config takes precedence over ENV)
        audio_config = buffer.get_audio_config(assistant_id)
        sample_rate = audio_config["sample_rate"]
        sample_width = audio_config["sample_width"]
        channels = audio_config["channels"]

        # Create metadata
        timestamp = datetime.utcnow().isoformat()
        metadata = {
            "timestamp": timestamp,
            "assistant_id": assistant_id,
            "pre_duration": pre_duration,
            "post_duration": post_duration,
            "sample_rate": sample_rate,
            "samples": len(clip),
            "duration": len(clip) / (sample_rate * channels),
        }

        # Write WAV file with assistant-specific audio configuration
        wav_path = writer.write_clip(
            clip,
            metadata=metadata,
            sample_rate=sample_rate,
            sample_width=sample_width,
            channels=channels,
        )

        clip_db.insert_clip(
            CLIP_DB_PATH,
            filename=Path(wav_path).name,
            timestamp=timestamp.replace("+00:00", "Z"),
            assistant_id=assistant_id,
            duration=metadata.get("duration"),
            sample_rate=sample_rate,
            label=clip_db.LABEL_UNKNOWN,
        )

        # Publish MQTT event
        mqtt_published = mqtt.publish_wake_event(wav_path, metadata)

        logger.info(f"Wake event processed for assistant {assistant_id}: {wav_path}")

        return {
            "success": True,
            "wav_file": wav_path,
            "metadata": metadata,
            "mqtt_published": mqtt_published,
        }

    except HTTPException:
        raise  # Re-raise HTTPException so it's not caught by the generic handler
    except Exception as e:
        logger.error(f"Error processing wake event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/capture_background_noise")
async def capture_background_noise(payload: CaptureBackgroundNoiseRequest):
    """
    Capture the last N seconds of audio and label as background noise.

    Args:
        payload: Request containing seconds and assistant_id

    Returns:
        Information about the saved clip
    """
    try:
        seconds = payload.seconds
        assistant_id = payload.assistant_id

        buffer = get_audio_buffer()
        writer = get_wav_writer()

        # Validate seconds parameter
        if seconds <= 0:
            raise HTTPException(
                status_code=400, detail="Seconds must be greater than 0"
            )

        if seconds > settings.BUFFER_DURATION_SECONDS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Seconds cannot exceed buffer duration "
                    f"({settings.BUFFER_DURATION_SECONDS}s)"
                ),
            )

        # Extract clip from buffer - capture last N seconds
        # We use pre_duration=seconds and post_duration=0 to get the last N seconds
        clip = await buffer.get_clip(
            assistant_id=assistant_id,
            pre_duration=seconds,
            post_duration=0,
            trigger_offset=0,
        )

        if clip is None:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient audio data in buffer for assistant {assistant_id}",
            )

        # Get audio configuration for this assistant
        audio_config = buffer.get_audio_config(assistant_id)
        sample_rate = audio_config["sample_rate"]
        sample_width = audio_config["sample_width"]
        channels = audio_config["channels"]

        # Create metadata
        timestamp = datetime.utcnow().isoformat()
        metadata = {
            "timestamp": timestamp,
            "assistant_id": assistant_id,
            "pre_duration": seconds,
            "post_duration": 0,
            "sample_rate": sample_rate,
            "samples": len(clip),
            "duration": len(clip) / (sample_rate * channels),
            "label": clip_db.LABEL_BACKGROUND_NOISE,
        }

        # Write WAV file with assistant-specific audio configuration
        wav_path = writer.write_clip(
            clip,
            metadata=metadata,
            sample_rate=sample_rate,
            sample_width=sample_width,
            channels=channels,
        )

        # Insert clip into database with Background Noise label
        clip_db.insert_clip(
            CLIP_DB_PATH,
            filename=Path(wav_path).name,
            timestamp=timestamp.replace("+00:00", "Z"),
            assistant_id=assistant_id,
            duration=metadata.get("duration"),
            sample_rate=sample_rate,
            label=clip_db.LABEL_BACKGROUND_NOISE,
        )

        logger.info(
            f"Background noise clip captured for assistant {assistant_id}: {wav_path}"
        )

        return {
            "success": True,
            "wav_file": wav_path,
            "metadata": metadata,
            "label": clip_db.LABEL_BACKGROUND_NOISE,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error capturing background noise: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear_buffer")
async def clear_buffer(assistant_id: Optional[str] = None):
    """
    Clear the audio buffer.

    Args:
        assistant_id: Specific assistant to clear, or None to clear all
    """
    buffer = get_audio_buffer()
    await buffer.clear(assistant_id)
    if assistant_id:
        return {
            "success": True,
            "message": f"Buffer cleared for assistant {assistant_id}",
        }
    return {"success": True, "message": "All buffers cleared"}


@app.websocket("/ws/audio")
async def websocket_audio_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for receiving raw PCM audio data.

    Expected format: Raw PCM 16-bit signed integers, little-endian
    """
    await websocket.accept()
    active_connections.append(websocket)

    buffer = get_audio_buffer()
    client_info = websocket.client
    logger.info(f"WebSocket client connected: {client_info}")

    try:
        while True:
            # Receive raw audio data
            data = await websocket.receive_bytes()

            # Append to buffer
            await buffer.append(data)

            # Optional: Send acknowledgment back to client
            # await websocket.send_json({"status": "ok", "bytes_received": len(data)})

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {client_info}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)


@app.post("/cleanup")
async def cleanup_old_files(max_age_days: int = 7):
    """
    Cleanup old WAV files.

    Args:
        max_age_days: Maximum age of files to keep (default: 7 days)

    Returns:
        Number of files deleted
    """
    writer = get_wav_writer()
    deleted_count = writer.cleanup_old_files(max_age_days)
    return {
        "success": True,
        "deleted_count": deleted_count,
        "max_age_days": max_age_days,
    }


@app.get("/api/clips")
async def list_clips(
    start: Optional[str] = None,
    end: Optional[str] = None,
    label: Optional[str] = None,
    include_deleted: bool = False,
):
    """List audio clips with optional datetime and label filtering."""
    start_dt = _parse_datetime(start) if start else None
    end_dt = _parse_datetime(end) if end else None

    start_iso = start_dt.isoformat().replace("+00:00", "Z") if start_dt else None
    end_iso = end_dt.isoformat().replace("+00:00", "Z") if end_dt else None

    rows = clip_db.list_clips(
        CLIP_DB_PATH,
        start=start_iso,
        end=end_iso,
        label=label,
        include_deleted=include_deleted,
    )
    clips = []
    for row in rows:
        clips.append(
            {
                "id": row["id"],
                "filename": row["filename"],
                "timestamp": row["timestamp"],
                "duration_seconds": row["duration"],
                "assistant_id": row["assistant_id"],
                "sample_rate": row["sample_rate"],
                "label": row["label"],
                "deleted": bool(row["deleted"]),
                "audio_url": f"/api/clips/{row['id']}/audio",
            }
        )

    return {"clips": clips}


@app.get("/api/clips/{clip_id}/audio")
async def get_clip_audio(clip_id: int = FastAPIPath(..., ge=1)):
    """Stream a WAV clip."""
    row = clip_db.get_clip(CLIP_DB_PATH, clip_id)
    if not row:
        raise HTTPException(status_code=404, detail="Clip not found")
    wav_path = _clip_path_from_filename(row["filename"])
    return FileResponse(wav_path)


@app.post("/api/clips/{clip_id}/label")
async def label_clip(
    payload: ClipLabelRequest,
    clip_id: int = FastAPIPath(..., ge=1),
):
    """Label a clip in the database."""
    label = payload.label
    if label not in CLIP_LABELS:
        raise HTTPException(status_code=400, detail="Invalid label")

    updated = clip_db.update_label(CLIP_DB_PATH, clip_id, label)
    if not updated:
        raise HTTPException(status_code=404, detail="Clip not found")

    row = clip_db.get_clip(CLIP_DB_PATH, clip_id)
    if row:
        wav_path = _clip_path_from_filename(row["filename"])
        metadata = _clip_metadata(wav_path)
        metadata["label"] = label
        metadata["reviewed_at"] = (
            datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
        )
        metadata_path = wav_path.with_suffix(".json")
        try:
            with open(metadata_path, "w") as metadata_file:
                json.dump(metadata, metadata_file, indent=2)
        except OSError:
            logger.warning("Failed to write metadata for %s", wav_path.name)

    return {
        "success": True,
        "clip_id": clip_id,
        "label": label,
    }


@app.post("/api/clips/{clip_id}/delete")
async def delete_clip(clip_id: int = FastAPIPath(..., ge=1)):
    """Soft-delete a clip (mark as deleted without removing from database)."""
    deleted = clip_db.soft_delete_clip(CLIP_DB_PATH, clip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Clip not found")

    row = clip_db.get_clip(CLIP_DB_PATH, clip_id)
    if row:
        wav_path = _clip_path_from_filename(row["filename"])
        metadata = _clip_metadata(wav_path)
        metadata["deleted"] = True
        metadata["deleted_at"] = (
            datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
        )
        metadata_path = wav_path.with_suffix(".json")
        try:
            with open(metadata_path, "w") as metadata_file:
                json.dump(metadata, metadata_file, indent=2)
        except OSError:
            logger.warning("Failed to write metadata for %s", wav_path.name)

    return {
        "success": True,
        "clip_id": clip_id,
        "deleted": True,
    }


@app.post("/api/clips/{clip_id}/undelete")
async def undelete_clip(clip_id: int = FastAPIPath(..., ge=1)):
    """Restore a soft-deleted clip."""
    undeleted = clip_db.undelete_clip(CLIP_DB_PATH, clip_id)
    if not undeleted:
        raise HTTPException(status_code=404, detail="Clip not found")

    row = clip_db.get_clip(CLIP_DB_PATH, clip_id)
    if row:
        wav_path = _clip_path_from_filename(row["filename"])
        metadata = _clip_metadata(wav_path)
        metadata["deleted"] = False
        metadata["undeleted_at"] = (
            datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
        )
        metadata_path = wav_path.with_suffix(".json")
        try:
            with open(metadata_path, "w") as metadata_file:
                json.dump(metadata, metadata_file, indent=2)
        except OSError:
            logger.warning("Failed to write metadata for %s", wav_path.name)

    return {
        "success": True,
        "clip_id": clip_id,
        "deleted": False,
    }


@app.get("/api/clips/download")
async def download_clips(
    start: Optional[str] = None,
    end: Optional[str] = None,
    label: Optional[str] = None,
    include_deleted: bool = False,
):
    """Download clips as a zip file organized by label."""
    start_dt = _parse_datetime(start) if start else None
    end_dt = _parse_datetime(end) if end else None

    start_iso = start_dt.isoformat().replace("+00:00", "Z") if start_dt else None
    end_iso = end_dt.isoformat().replace("+00:00", "Z") if end_dt else None

    # Get clips matching the filter
    rows = clip_db.list_clips(
        CLIP_DB_PATH,
        start=start_iso,
        end=end_iso,
        label=label,
        include_deleted=include_deleted,
    )

    if not rows:
        raise HTTPException(
            status_code=404, detail="No clips found matching the criteria"
        )

    # Create a temporary zip file
    temp_dir = Path(tempfile.mkdtemp())
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    label_suffix = f"_{label.replace(' ', '_')}" if label else "_all"
    zip_filename = f"clips{label_suffix}_{timestamp}.zip"
    zip_path = temp_dir / zip_filename

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Organize clips by label
            for row in rows:
                clip_label = row["label"] or "Unknown"
                label_dir = clip_label.replace(" ", "_")

                # Get the WAV file
                wav_path = _clip_path_from_filename(row["filename"])
                if not wav_path.exists():
                    logger.warning(f"WAV file not found: {wav_path}")
                    continue

                # Add WAV file to zip
                arcname = f"{label_dir}/{wav_path.name}"
                zipf.write(wav_path, arcname)

                # Add metadata JSON if it exists
                metadata_path = wav_path.with_suffix(".json")
                if metadata_path.exists():
                    arcname = f"{label_dir}/{metadata_path.name}"
                    zipf.write(metadata_path, arcname)

        # Return the zip file with background task to cleanup temp directory
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=zip_filename,
            headers={"Content-Disposition": f"attachment; filename={zip_filename}"},
            background=lambda: _cleanup_temp_dir(temp_dir),
        )
    except Exception as e:
        # Clean up on error
        _cleanup_temp_dir(temp_dir)
        logger.error(f"Error creating zip file: {e}")
        raise HTTPException(
            status_code=500, detail="Error creating zip file. Please try again."
        )


def _cleanup_temp_dir(temp_dir: Path) -> None:
    """Clean up temporary directory and its contents."""
    try:
        import shutil

        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    except Exception as e:
        logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")


def main():
    """Run the FastAPI application."""
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
