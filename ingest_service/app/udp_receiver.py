import asyncio
from dataclasses import dataclass
import logging
import re
import struct
from typing import Callable, Optional

from .config import settings

logger = logging.getLogger(__name__)

UDP_PACKET_V1_MAGIC = b"WWD1"
UDP_PACKET_MAGIC = b"WWD2"
UDP_AUDIO_ENCODING_PCM_SIGNED_LE = 1
UDP_PACKET_FIXED_HEADER = struct.Struct("!4sBBBBIIH")
MAX_ASSISTANT_ID_BYTES = 64
ASSISTANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class UDPAudioPacketMetadata:
    sample_rate: int
    bits_per_sample: int
    channels: int
    encoding: int
    sequence: int


def encode_udp_audio_packet(
    assistant_id: str,
    pcm_data: bytes,
    *,
    sample_rate: int = 16000,
    bits_per_sample: int = 16,
    channels: int = 1,
    encoding: int = UDP_AUDIO_ENCODING_PCM_SIGNED_LE,
    sequence: int = 0,
) -> bytes:
    """Frame PCM and its format so it survives UDP proxies such as Traefik.

    All multi-byte integers are network byte order. The fixed header is followed
    by the ASCII assistant ID and then the unchanged PCM bytes.
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
    if not 1 <= channels <= 255:
        raise ValueError("channels must be between 1 and 255")
    if bits_per_sample not in (8, 16, 24, 32):
        raise ValueError("bits_per_sample must be 8, 16, 24, or 32")
    if not 1 <= sample_rate <= 0xFFFFFFFF:
        raise ValueError("sample_rate must be between 1 and 4294967295")
    if not 0 <= sequence <= 0xFFFFFFFF:
        raise ValueError("sequence must be between 0 and 4294967295")
    if len(pcm_data) > 0xFFFF:
        raise ValueError("pcm_data exceeds the UDP packet payload limit")
    header = UDP_PACKET_FIXED_HEADER.pack(
        UDP_PACKET_MAGIC,
        len(encoded_id),
        channels,
        bits_per_sample,
        encoding,
        sample_rate,
        sequence,
        len(pcm_data),
    )
    return header + encoded_id + pcm_data


def _decode_udp_audio_packet(
    data: bytes,
    fallback_assistant_id: str,
) -> Optional[tuple[str, bytes, Optional[UDPAudioPacketMetadata]]]:
    """Decode a framed packet, or treat a non-magic packet as legacy raw PCM."""
    if data.startswith(UDP_PACKET_MAGIC):
        if len(data) < UDP_PACKET_FIXED_HEADER.size:
            return None
        (
            _magic,
            id_length,
            channels,
            bits_per_sample,
            encoding,
            sample_rate,
            sequence,
            payload_length,
        ) = UDP_PACKET_FIXED_HEADER.unpack_from(data)
        header_length = UDP_PACKET_FIXED_HEADER.size + id_length
        if (
            not 1 <= id_length <= MAX_ASSISTANT_ID_BYTES
            or channels == 0
            or bits_per_sample not in (8, 16, 24, 32)
            or sample_rate == 0
            or encoding != UDP_AUDIO_ENCODING_PCM_SIGNED_LE
            or payload_length == 0
            or len(data) != header_length + payload_length
        ):
            return None
        id_start = UDP_PACKET_FIXED_HEADER.size
        try:
            assistant_id = data[id_start:header_length].decode("ascii")
        except UnicodeDecodeError:
            return None
        if ASSISTANT_ID_PATTERN.fullmatch(assistant_id) is None:
            return None
        metadata = UDPAudioPacketMetadata(
            sample_rate=sample_rate,
            bits_per_sample=bits_per_sample,
            channels=channels,
            encoding=encoding,
            sequence=sequence,
        )
        return assistant_id, data[header_length:], metadata

    if not data.startswith(UDP_PACKET_V1_MAGIC):
        return fallback_assistant_id, data, None

    if len(data) <= len(UDP_PACKET_V1_MAGIC):
        return None
    id_length = data[len(UDP_PACKET_V1_MAGIC)]
    header_length = len(UDP_PACKET_V1_MAGIC) + 1 + id_length
    if not 1 <= id_length <= MAX_ASSISTANT_ID_BYTES or len(data) <= header_length:
        return None

    try:
        assistant_id = data[len(UDP_PACKET_V1_MAGIC) + 1 : header_length].decode("ascii")
    except UnicodeDecodeError:
        return None
    if ASSISTANT_ID_PATTERN.fullmatch(assistant_id) is None:
        return None
    return assistant_id, data[header_length:], None


class _AudioDatagramProtocol(asyncio.DatagramProtocol):
    """asyncio protocol that forwards each received datagram to an audio callback.

    Preferred packets contain an assistant ID followed by PCM. Legacy raw PCM
    (int16 / mono / 16 kHz, little-endian) remains supported using source-IP
    identity for direct, unproxied deployments.
    """

    def __init__(
        self,
        audio_callback: Callable[[str, bytes, Optional[UDPAudioPacketMetadata]], None],
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
        assistant_id, pcm_data, metadata = decoded
        # A fixed receiver ID remains an explicit override for single-assistant
        # deployments, even when the sender uses the framed protocol.
        assistant_id = self._assistant_id or assistant_id
        try:
            self._audio_callback(assistant_id, pcm_data, metadata)
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
        self._audio_callback: Optional[
            Callable[[str, bytes, Optional[UDPAudioPacketMetadata]], None]
        ] = None
        self.running = False

        logger.info(
            "UDPAudioReceiver initialized: %s:%s (assistant_id=%s)",
            host,
            port,
            self.assistant_id or "<sender-ip>",
        )

    def set_audio_callback(
        self,
        callback: Callable[[str, bytes, Optional[UDPAudioPacketMetadata]], None],
    ) -> None:
        """Set callback: callback(assistant_id, pcm_bytes, packet_metadata)."""
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
