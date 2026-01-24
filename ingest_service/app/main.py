import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

from .config import settings
from .audio_buffer import AudioBuffer
from .wav_writer import WAVWriter
from .mqtt_publisher import MQTTPublisher

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

# Initialize components
audio_buffer = AudioBuffer()
wav_writer = WAVWriter()
mqtt_publisher = MQTTPublisher()

# Track active websocket connections
active_connections: list[WebSocket] = []


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting Wake Word Audio Ingest Service...")
    logger.info(f"Server: {settings.HOST}:{settings.PORT}")
    logger.info(f"Sample Rate: {settings.SAMPLE_RATE} Hz")
    logger.info(f"Buffer Duration: {settings.BUFFER_DURATION_SECONDS}s")
    logger.info(f"Output Directory: {settings.OUTPUT_DIR}")
    
    # Connect to MQTT broker
    if mqtt_publisher.connect():
        logger.info("MQTT connection established")
    else:
        logger.warning("Failed to connect to MQTT broker")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down Wake Word Audio Ingest Service...")
    mqtt_publisher.disconnect()


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Wake Word Audio Ingest Service",
        "version": "1.0.0",
        "status": "running",
        "buffer_duration": audio_buffer.get_duration(),
        "active_connections": len(active_connections)
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "mqtt_connected": mqtt_publisher.connected,
        "buffer_samples": audio_buffer.get_buffer_size(),
        "buffer_duration_seconds": audio_buffer.get_duration()
    }


@app.post("/wake_event")
async def trigger_wake_event(
    pre_duration: float = settings.PRE_WAKE_DURATION_SECONDS,
    post_duration: float = settings.POST_WAKE_DURATION_SECONDS
):
    """
    Manually trigger a wake event to capture and save an audio clip.
    
    Args:
        pre_duration: Seconds of audio before the event
        post_duration: Seconds of audio after the event
    
    Returns:
        Information about the saved clip
    """
    try:
        # Extract clip from buffer
        clip = await audio_buffer.get_clip(
            pre_duration=pre_duration,
            post_duration=post_duration
        )
        
        if clip is None:
            raise HTTPException(
                status_code=400,
                detail="Insufficient audio data in buffer"
            )
        
        # Create metadata
        timestamp = datetime.utcnow().isoformat()
        metadata = {
            "timestamp": timestamp,
            "pre_duration": pre_duration,
            "post_duration": post_duration,
            "sample_rate": settings.SAMPLE_RATE,
            "samples": len(clip),
            "duration": len(clip) / settings.SAMPLE_RATE
        }
        
        # Write WAV file
        wav_path = wav_writer.write_clip(clip, metadata=metadata)
        
        # Publish MQTT event
        mqtt_published = mqtt_publisher.publish_wake_event(wav_path, metadata)
        
        logger.info(f"Wake event processed: {wav_path}")
        
        return {
            "success": True,
            "wav_file": wav_path,
            "metadata": metadata,
            "mqtt_published": mqtt_published
        }
        
    except Exception as e:
        logger.error(f"Error processing wake event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear_buffer")
async def clear_buffer():
    """Clear the audio buffer."""
    await audio_buffer.clear()
    return {"success": True, "message": "Buffer cleared"}


@app.websocket("/ws/audio")
async def websocket_audio_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for receiving raw PCM audio data.
    
    Expected format: Raw PCM 16-bit signed integers, little-endian
    """
    await websocket.accept()
    active_connections.append(websocket)
    
    client_info = websocket.client
    logger.info(f"WebSocket client connected: {client_info}")
    
    try:
        while True:
            # Receive raw audio data
            data = await websocket.receive_bytes()
            
            # Append to buffer
            await audio_buffer.append(data)
            
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
    deleted_count = wav_writer.cleanup_old_files(max_age_days)
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
