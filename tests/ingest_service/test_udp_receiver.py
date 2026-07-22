"""Tests for the UDP audio receiver and the UDP audio ingest handler."""

import asyncio
import os
import socket
import tempfile

import numpy as np
import pytest
from unittest.mock import patch

from ingest_service.app.udp_receiver import (
    UDPAudioReceiver,
    UDP_AUDIO_ENCODING_PCM_SIGNED_LE,
    encode_udp_audio_packet,
)


def _find_free_udp_port() -> int:
    """Grab an ephemeral UDP port, then release it for the receiver to bind."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.mark.asyncio
class TestUDPAudioReceiver:
    """Test cases for the UDPAudioReceiver."""

    async def test_start_requires_callback(self):
        """Receiver refuses to start without an audio callback."""
        rx = UDPAudioReceiver(host="127.0.0.1", port=_find_free_udp_port())
        assert await rx.start() is False
        assert rx.running is False

    async def test_receives_datagram_and_uses_sender_ip(self):
        """A datagram is forwarded with the sender IP as the assistant ID."""
        received = []
        port = _find_free_udp_port()
        rx = UDPAudioReceiver(host="127.0.0.1", port=port, assistant_id="")
        rx.set_audio_callback(
            lambda aid, data, metadata: received.append((aid, data, metadata))
        )
        assert await rx.start() is True

        try:
            payload = np.arange(128, dtype="<i2").tobytes()
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(payload, ("127.0.0.1", port))
            await asyncio.sleep(0.2)
        finally:
            rx.stop()
            sock.close()

        assert len(received) == 1
        assistant_id, data, metadata = received[0]
        assert assistant_id == "127.0.0.1"
        assert data == payload
        assert metadata is None

    async def test_fixed_assistant_id(self):
        """A configured assistant ID overrides the sender IP."""
        received = []
        port = _find_free_udp_port()
        rx = UDPAudioReceiver(host="127.0.0.1", port=port, assistant_id="sat1")
        rx.set_audio_callback(
            lambda aid, data, metadata: received.append((aid, data, metadata))
        )
        assert await rx.start() is True

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(b"\x00\x01\x02\x03", ("127.0.0.1", port))
            await asyncio.sleep(0.2)
        finally:
            rx.stop()
            sock.close()

        assert received
        assert received[0][0] == "sat1"

    async def test_fixed_assistant_id_overrides_framed_id(self):
        """The explicit single-assistant setting remains the final override."""
        received = []
        port = _find_free_udp_port()
        rx = UDPAudioReceiver(host="127.0.0.1", port=port, assistant_id="sat1")
        rx.set_audio_callback(
            lambda aid, data, metadata: received.append((aid, data, metadata))
        )
        assert await rx.start() is True

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(
                encode_udp_audio_packet("kitchen", b"\x00\x01", sequence=7),
                ("127.0.0.1", port),
            )
            await asyncio.sleep(0.2)
        finally:
            rx.stop()
            sock.close()

        assert received[0][:2] == ("sat1", b"\x00\x01")

    async def test_framed_datagram_uses_embedded_assistant_id(self):
        """A framed packet keeps assistant identity through a UDP proxy."""
        received = []
        port = _find_free_udp_port()
        rx = UDPAudioReceiver(host="127.0.0.1", port=port)
        rx.set_audio_callback(
            lambda aid, data, metadata: received.append((aid, data, metadata))
        )
        assert await rx.start() is True

        try:
            pcm = np.arange(128, dtype="<i2").tobytes()
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(
                encode_udp_audio_packet(
                    "kitchen",
                    pcm,
                    sample_rate=48000,
                    bits_per_sample=32,
                    channels=2,
                    sequence=42,
                ),
                ("127.0.0.1", port),
            )
            await asyncio.sleep(0.2)
        finally:
            rx.stop()
            sock.close()

        assert received[0][:2] == ("kitchen", pcm)
        metadata = received[0][2]
        assert metadata.sample_rate == 48000
        assert metadata.bits_per_sample == 32
        assert metadata.channels == 2
        assert metadata.encoding == UDP_AUDIO_ENCODING_PCM_SIGNED_LE
        assert metadata.sequence == 42

    async def test_rejects_framed_datagram_with_wrong_payload_length(self):
        received = []
        port = _find_free_udp_port()
        rx = UDPAudioReceiver(host="127.0.0.1", port=port)
        rx.set_audio_callback(
            lambda aid, data, metadata: received.append((aid, data, metadata))
        )
        assert await rx.start() is True

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            packet = encode_udp_audio_packet("kitchen", b"\x00\x01", sequence=1)
            sock.sendto(packet[:-1], ("127.0.0.1", port))
            await asyncio.sleep(0.2)
        finally:
            rx.stop()
            sock.close()

        assert received == []

    async def test_accepts_legacy_wwd1_framed_datagram(self):
        received = []
        port = _find_free_udp_port()
        rx = UDPAudioReceiver(host="127.0.0.1", port=port)
        rx.set_audio_callback(
            lambda aid, data, metadata: received.append((aid, data, metadata))
        )
        assert await rx.start() is True

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(b"WWD1\x07kitchen\x00\x01", ("127.0.0.1", port))
            await asyncio.sleep(0.2)
        finally:
            rx.stop()
            sock.close()

        assert received == [("kitchen", b"\x00\x01", None)]

    async def test_malformed_framed_datagram_is_ignored(self):
        """Packets claiming to be framed must not leak header bytes into PCM."""
        received = []
        port = _find_free_udp_port()
        rx = UDPAudioReceiver(host="127.0.0.1", port=port)
        rx.set_audio_callback(
            lambda aid, data, metadata: received.append((aid, data, metadata))
        )
        assert await rx.start() is True

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(b"WWD1\x08short", ("127.0.0.1", port))
            await asyncio.sleep(0.2)
        finally:
            rx.stop()
            sock.close()

        assert received == []

    async def test_empty_datagram_ignored(self):
        """Zero-length datagrams do not invoke the callback."""
        received = []
        port = _find_free_udp_port()
        rx = UDPAudioReceiver(host="127.0.0.1", port=port)
        rx.set_audio_callback(
            lambda aid, data, metadata: received.append((aid, data, metadata))
        )
        assert await rx.start() is True

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(b"", ("127.0.0.1", port))
            await asyncio.sleep(0.2)
        finally:
            rx.stop()
            sock.close()

        assert received == []


@pytest.mark.asyncio
class TestHandleUDPAudioData:
    """Test the UDP audio ingest handler configures buffers correctly."""

    async def test_configures_buffer_for_udp_format_once(self):
        """First datagram sets the UDP audio config; subsequent ones don't reconfigure."""
        with patch.dict(
            os.environ,
            {"OUTPUT_DIR": tempfile.mkdtemp(), "MQTT_BROKER": "test-broker"},
        ):
            import ingest_service.app.main as main_module

        main_module.audio_buffer = None
        main_module.udp_configured_assistants = set()

        # int16 mono @ 16 kHz => 2 bytes per sample
        payload = np.arange(160, dtype="<i2").tobytes()

        await main_module.handle_udp_audio_data("192.168.1.50", payload, None)

        buffer = main_module.get_audio_buffer()
        config = buffer.get_audio_config("192.168.1.50")
        assert config["sample_rate"] == 16000
        assert config["sample_width"] == 2
        assert config["channels"] == 1
        assert buffer.get_buffer_size("192.168.1.50") == 160
        assert "192.168.1.50" in main_module.udp_configured_assistants

        # A second datagram should append without recreating the buffer.
        await main_module.handle_udp_audio_data("192.168.1.50", payload, None)
        assert buffer.get_buffer_size("192.168.1.50") == 320

    async def test_uses_packet_audio_metadata(self):
        with patch.dict(
            os.environ,
            {"OUTPUT_DIR": tempfile.mkdtemp(), "MQTT_BROKER": "test-broker"},
        ):
            import ingest_service.app.main as main_module
            from ingest_service.app.udp_receiver import UDPAudioPacketMetadata

        main_module.audio_buffer = None
        main_module.udp_configured_assistants = set()
        metadata = UDPAudioPacketMetadata(
            sample_rate=48000,
            bits_per_sample=32,
            channels=2,
            encoding=UDP_AUDIO_ENCODING_PCM_SIGNED_LE,
            sequence=9,
        )

        await main_module.handle_udp_audio_data("kitchen", b"\x00" * 16, metadata)

        config = main_module.get_audio_buffer().get_audio_config("kitchen")
        assert config["sample_rate"] == 48000
        assert config["sample_width"] == 4
        assert config["channels"] == 2
