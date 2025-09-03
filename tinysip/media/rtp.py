# rtp.py
# RTP packet packing/unpacking and simple UDP sender/receiver

import asyncio
import socket
import struct
from dataclasses import dataclass


@dataclass
class RTPHeader:
    version: int = 2
    padding: int = 0
    extension: int = 0
    csrc_count: int = 0
    marker: int = 0
    payload_type: int = 0  # e.g., 0 (PCMU), 8 (PCMA) if applicable
    sequence_number: int = 0
    timestamp: int = 0
    ssrc: int = 0

    def pack(self) -> bytes:
        b0 = (
            (self.version & 0x3) << 6
            | (self.padding & 0x1) << 5
            | (self.extension & 0x1) << 4
            | (self.csrc_count & 0xF)
        )
        b1 = (self.marker & 0x1) << 7 | (self.payload_type & 0x7F)
        return struct.pack(
            "!BBHII",
            b0,
            b1,
            self.sequence_number & 0xFFFF,
            self.timestamp & 0xFFFFFFFF,
            self.ssrc & 0xFFFFFFFF,
        )

    @staticmethod
    def unpack(buf: bytes) -> "RTPHeader":
        if len(buf) < 12:
            raise ValueError("RTP header requires at least 12 bytes")
        b0, b1, seq, ts, ssrc = struct.unpack("!BBHII", buf[:12])
        return RTPHeader(
            version=(b0 >> 6) & 0x03,
            padding=(b0 >> 5) & 0x01,
            extension=(b0 >> 4) & 0x01,
            csrc_count=b0 & 0x0F,
            marker=(b1 >> 7) & 0x01,
            payload_type=b1 & 0x7F,
            sequence_number=seq,
            timestamp=ts,
            ssrc=ssrc,
        )


@dataclass
class RTPPacket:
    header: RTPHeader
    payload: bytes

    def to_bytes(self) -> bytes:
        return self.header.pack() + self.payload

    @staticmethod
    def from_bytes(buf: bytes) -> "RTPPacket":
        hdr = RTPHeader.unpack(buf)
        payload = buf[12 + 4 * hdr.csrc_count :]
        return RTPPacket(hdr, payload)


class RTPSession:
    """Minimal RTP UDP session (send/recv) with sequencing and timestamping."""

    def __init__(self, ssrc: int, payload_type: int = 0, clock_rate: int = 8000):
        self.ssrc = ssrc
        self.payload_type = payload_type
        self.clock_rate = clock_rate
        self.seq = 0
        self.ts = 0
        self.sock: socket.socket | None = None

    def bind(self, host: str = "0.0.0.0", port: int = 0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.sock.setblocking(False)

    async def send(
        self, payload: bytes, dest: tuple[str, int], marker: int = 0, ts_incr: int = 160
    ):
        if not self.sock:
            raise RuntimeError("Socket not bound")
        hdr = RTPHeader(
            marker=marker,
            payload_type=self.payload_type,
            sequence_number=self.seq,
            timestamp=self.ts,
            ssrc=self.ssrc,
        )
        pkt = RTPPacket(hdr, payload).to_bytes()
        loop = asyncio.get_running_loop()
        await loop.sock_sendto(self.sock, pkt, dest)
        self.seq = (self.seq + 1) & 0xFFFF
        self.ts = (self.ts + ts_incr) & 0xFFFFFFFF

    async def recv(self, bufsize: int = 2048) -> RTPPacket:
        if not self.sock:
            raise RuntimeError("Socket not bound")
        loop = asyncio.get_running_loop()
        data, _ = await loop.sock_recvfrom(self.sock, bufsize)
        return RTPPacket.from_bytes(data)

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None
