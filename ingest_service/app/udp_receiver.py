import asyncio
import logging
import re
from typing import Callable, Optional

from .config import settings

logger = logging.getLogger(__name__)

UDP_PACKET_MAGIC = b"WWD1"
MAX_ASSISTANT_ID_BYTES = 64
ASSISTANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def encode_udp_audio_packet(assistant_id: str, pcm_data: bytes) -> bytes:
    """Frame PCM with an assistant ID that survives UDP proxies such as Traefik.

    Wire format: ``WWD1`` magic, one-byte ID length, ASCII assistant ID, then
    the unchanged PCM bytes.
    """
    try:
        encoded_id = assistant_id.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("assistant_id must be ASCII") from exc
    if not 1 <= len(encoded_id) <= MAX_ASSISTANT_ID_BYTES:
        raise ValueError("assistant_id must contain 1 to 64 ASCII bytes")
    if ASSISTANT_ID_PATTERN.fullmatch(assistant_id) is None:
        raise ValueError(
            "assistant_id must start with an alphanumeric character and contain "
            "only letters, numbers, underscores, periods, or hyphens"
        )
    if not pcm_data:
        raise ValueError("pcm_data must not be empty")
    return UDP_PACKET_MAGIC + bytes((len(encoded_id),)) + encoded_id + pcm_data


def _decode_udp_audio_packet(
    data: bytes,
    fallback_assistant_id: str,
) -> Optional[tuple[str, bytes]]:
    """Decode a framed packet, or treat a non-magic packet as legacy raw PCM."""
    if not data.startswith(UDP_PACKET_MAGIC):
        return fallback_assistant_id, data

    if len(data) <= len(UDP_PACKET_MAGIC):
        return None
    id_length = data[len(UDP_PACKET_MAGIC)]
    header_length = len(UDP_PACKET_MAGIC) + 1 + id_length
    if not 1 <= id_length <= MAX_ASSISTANT_ID_BYTES or len(data) <= header_length:
        return None

    try:
        assistant_id = data[len(UDP_PACKET_MAGIC) + 1 : header_length].decode("ascii")
    except UnicodeDecodeError:
        return None
    if ASSISTANT_ID_PATTERN.fullmatch(assistant_id) is None:
        return None
    return assistant_id, data[header_length:]


class _AudioDatagramProtocol(asyncio.DatagramProtocol):
    """asyncio protocol that forwards each received datagram to an audio callback.

    Preferred packets contain an assistant ID followed by PCM. Legacy raw PCM
    (int16 / mono / 16 kHz, little-endian) remains supported using source-IP
    identity for direct, unproxied deployments.
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
        fallback_assistant_id = self._assistant_id or addr[0]
        decoded = _decode_udp_audio_packet(data, fallback_assistant_id)
        if decoded is None:
            logger.warning("Ignoring malformed framed UDP audio datagram from %s", addr)
            return
        assistant_id, pcm_data = decoded
        # A fixed receiver ID remains an explicit override for single-assistant
        # deployments, even when the sender uses the framed protocol.
        assistant_id = self._assistant_id or assistant_id
        try:
            self._audio_callback(assistant_id, pcm_data)
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
