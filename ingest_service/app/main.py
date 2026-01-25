import logging
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

from .config import settings
from .audio_buffer import AudioBuffer, MultiAssistantAudioBuffer
from .wav_writer import WAVWriter
from .mqtt_publisher import MQTTPublisher
from .mqtt_subscriber import MQTTSubscriber

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Wake Word Audio Ingest Service",
    description="Receives audio streams, buffers, and saves wake word clips",
    version="1.0.0"
)

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


async def handle_audio_data(assistant_id: str, audio_data: bytes) -> None:
    """Handle incoming audio data from MQTT."""
    buffer = get_audio_buffer()
    await buffer.append(assistant_id, audio_data)
    logger.debug(f"Received {len(audio_data)} bytes of audio data for assistant {assistant_id}")


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
        await buffer.set_audio_config(assistant_id, sample_rate, bits_per_sample, channels)
        
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
        logger.info(f"Waiting {post_duration}s to capture post-wake audio for assistant {assistant_id}")
        await asyncio.sleep(post_duration)
        
        # Extract clip from buffer for this assistant
        # Use trigger_offset to indicate the wake event was post_duration seconds ago
        clip = await buffer.get_clip(
            assistant_id=assistant_id,
            pre_duration=pre_duration,
            post_duration=post_duration,
            trigger_offset=post_duration
        )
        
        if clip is None:
            logger.warning(f"Insufficient audio data in buffer for assistant {assistant_id}")
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
            "wake_metadata": metadata
        }
        
        # Write WAV file with assistant-specific audio configuration
        wav_path = writer.write_clip(
            clip,
            metadata=clip_metadata,
            sample_rate=sample_rate,
            sample_width=sample_width,
            channels=channels
        )
        
        # Publish MQTT event
        mqtt.publish_wake_event(wav_path, clip_metadata)
        
        logger.info(f"Wake event processed for assistant {assistant_id}: {wav_path}")
        
    except Exception as e:
        logger.error(f"Error processing wake event from MQTT for assistant {assistant_id}: {e}")



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
    
    # Initialize components
    get_audio_buffer()
    get_wav_writer()
    
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
            asyncio.run_coroutine_threadsafe(handle_audio_data(assistant_id, data), main_event_loop)
    
    def audio_info_callback(assistant_id: str, audio_info: dict):
        """Thread-safe wrapper for async audio info handler."""
        if main_event_loop and not main_event_loop.is_closed():
            asyncio.run_coroutine_threadsafe(handle_audio_info(assistant_id, audio_info), main_event_loop)
    
    def wake_callback(assistant_id: str, metadata: dict):
        """Thread-safe wrapper for async wake handler."""
        if main_event_loop and not main_event_loop.is_closed():
            asyncio.run_coroutine_threadsafe(handle_wake_event(assistant_id, metadata), main_event_loop)
    
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
        "active_assistants": buffer.get_assistant_ids()
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
        "active_assistants": buffer.get_assistant_ids()
    }


@app.post("/wake_event")
async def trigger_wake_event(
    assistant_id: str = "default",
    pre_duration: float = settings.PRE_WAKE_DURATION_SECONDS,
    post_duration: float = settings.POST_WAKE_DURATION_SECONDS
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
        logger.info(f"Waiting {post_duration}s to capture post-wake audio for assistant {assistant_id}")
        await asyncio.sleep(post_duration)
        
        # Extract clip from buffer for this assistant
        # Use trigger_offset to indicate the wake event was post_duration seconds ago
        clip = await buffer.get_clip(
            assistant_id=assistant_id,
            pre_duration=pre_duration,
            post_duration=post_duration,
            trigger_offset=post_duration
        )
        
        if clip is None:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient audio data in buffer for assistant {assistant_id}"
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
            "duration": len(clip) / (sample_rate * channels)
        }
        
        # Write WAV file with assistant-specific audio configuration
        wav_path = writer.write_clip(
            clip,
            metadata=metadata,
            sample_rate=sample_rate,
            sample_width=sample_width,
            channels=channels
        )
        
        # Publish MQTT event
        mqtt_published = mqtt.publish_wake_event(wav_path, metadata)
        
        logger.info(f"Wake event processed for assistant {assistant_id}: {wav_path}")
        
        return {
            "success": True,
            "wav_file": wav_path,
            "metadata": metadata,
            "mqtt_published": mqtt_published
        }
        
    except HTTPException:
        raise  # Re-raise HTTPException so it's not caught by the generic handler
    except Exception as e:
        logger.error(f"Error processing wake event: {e}")
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
        return {"success": True, "message": f"Buffer cleared for assistant {assistant_id}"}
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
        "max_age_days": max_age_days
    }


def main():
    """Run the FastAPI application."""
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
