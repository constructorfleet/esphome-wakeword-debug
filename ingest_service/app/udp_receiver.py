import asyncio
import logging
from typing import Callable, Optional

from .config import settings

logger = logging.getLogger(__name__)


class _AudioDatagramProtocol(asyncio.DatagramProtocol):
    """asyncio protocol that forwards each received datagram to an audio callback.

    The satellite1 `wake_audio_stream` component sends raw, unframed PCM
    (int16 / mono / 16 kHz, little-endian). Each datagram is a chunk of that
    stream, so we hand the raw bytes straight to the callback.
    """

    def __init__(
        self,
        audio_callback: Callable[[str, bytes], None],
        assistant_id: Optional[str],
    ):
        self._audio_callback = audio_callback
        self._assistant_id = assistant_id

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        if not data:
            return
        # Attribute the audio to the configured assistant, or fall back to the
        # sender's IP so multiple devices stay in separate buffers.
        assistant_id = self._assistant_id or addr[0]
        try:
            self._audio_callback(assistant_id, data)
        except Exception:
            logger.exception("Error handling UDP audio datagram from %s", addr)

    def error_received(self, exc: Exception) -> None:
        logger.warning("UDP receiver error: %s", exc)


class UDPAudioReceiver:
    """Listens for raw PCM audio over UDP and forwards it to a callback.

    Runs on the provided asyncio event loop (the same loop FastAPI uses), so the
    audio callback can schedule coroutines directly without cross-thread hops.
    """

    def __init__(
        self,
        host: str = settings.UDP_HOST,
        port: int = settings.UDP_PORT,
        assistant_id: str = settings.UDP_ASSISTANT_ID,
    ):
        self.host = host
        self.port = port
        # Empty string means "derive from sender IP"; normalize to None.
        self.assistant_id: Optional[str] = assistant_id or None

        self._transport: Optional[asyncio.DatagramTransport] = None
        self._audio_callback: Optional[Callable[[str, bytes], None]] = None
        self.running = False

        logger.info(
            "UDPAudioReceiver initialized: %s:%s (assistant_id=%s)",
            host,
            port,
            self.assistant_id or "<sender-ip>",
        )

    def set_audio_callback(self, callback: Callable[[str, bytes], None]) -> None:
        """Set callback for handling audio data: callback(assistant_id, pcm_bytes)."""
        self._audio_callback = callback

    async def start(self) -> bool:
        """Bind the UDP socket and begin receiving. Returns True on success."""
        if self._audio_callback is None:
            logger.error("Cannot start UDP receiver: no audio callback set")
            return False

        loop = asyncio.get_running_loop()
        try:
            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _AudioDatagramProtocol(self._audio_callback, self.assistant_id),
                local_addr=(self.host, self.port),
            )
        except OSError as exc:
            logger.error("Failed to bind UDP receiver to %s:%s: %s", self.host, self.port, exc)
            return False

        self.running = True
        logger.info("UDP audio receiver listening on %s:%s", self.host, self.port)
        return True

    def stop(self) -> None:
        """Close the UDP socket."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self.running = False
        logger.info("UDP audio receiver stopped")
