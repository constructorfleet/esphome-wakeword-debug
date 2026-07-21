"""Tests for the UDP audio receiver and the UDP audio ingest handler."""

import asyncio
import os
import socket
import tempfile

import numpy as np
import pytest
from unittest.mock import patch

from ingest_service.app.udp_receiver import UDPAudioReceiver


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
        rx.set_audio_callback(lambda aid, data: received.append((aid, data)))
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
        assistant_id, data = received[0]
        assert assistant_id == "127.0.0.1"
        assert data == payload

    async def test_fixed_assistant_id(self):
        """A configured assistant ID overrides the sender IP."""
        received = []
        port = _find_free_udp_port()
        rx = UDPAudioReceiver(host="127.0.0.1", port=port, assistant_id="sat1")
        rx.set_audio_callback(lambda aid, data: received.append((aid, data)))
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

    async def test_empty_datagram_ignored(self):
        """Zero-length datagrams do not invoke the callback."""
        received = []
        port = _find_free_udp_port()
        rx = UDPAudioReceiver(host="127.0.0.1", port=port)
        rx.set_audio_callback(lambda aid, data: received.append((aid, data)))
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

        await main_module.handle_udp_audio_data("192.168.1.50", payload)

        buffer = main_module.get_audio_buffer()
        config = buffer.get_audio_config("192.168.1.50")
        assert config["sample_rate"] == 16000
        assert config["sample_width"] == 2
        assert config["channels"] == 1
        assert buffer.get_buffer_size("192.168.1.50") == 160
        assert "192.168.1.50" in main_module.udp_configured_assistants

        # A second datagram should append without recreating the buffer.
        await main_module.handle_udp_audio_data("192.168.1.50", payload)
        assert buffer.get_buffer_size("192.168.1.50") == 320
