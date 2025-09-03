# codecs_dtmf_audio.py

import struct

# ===== G.711 (PCMU/PCMA) =====


class G711:
    """Codec G.711 PCMU (μ-law) e PCMA (A-law) com conversão PCM16 <-> 8-bit."""

    @staticmethod
    def linear2ulaw(sample: int) -> int:
        """Converte PCM16 (signed) em PCMU 8-bit."""
        # Clamp
        if sample > 32767:
            sample = 32767
        if sample < -32768:
            sample = -32768
        BIAS = 0x84
        MAX = 32635

        sign = 0 if sample >= 0 else 0x80
        if sign != 0:
            sample = -sample
        if sample > MAX:
            sample = MAX
        sample = sample + BIAS
        # segment
        seg = 7
        for i in range(7):
            if sample <= (0x1F << (i + 3)):
                seg = i
                break
        mant = (sample >> (seg + 3)) & 0x0F
        ulaw = ~(sign | (seg << 4) | mant) & 0xFF
        return ulaw

    @staticmethod
    def ulaw2linear(u_val: int) -> int:
        """Converte PCMU 8-bit em PCM16 (signed)."""
        u_val = ~u_val & 0xFF
        sign = u_val & 0x80
        seg = (u_val >> 4) & 0x07
        mant = u_val & 0x0F
        sample = ((mant | 0x10) << (seg + 3)) - 0x84
        return -sample if sign else sample

    @staticmethod
    def linear2alaw(sample: int) -> int:
        """Converte PCM16 (signed) em PCMA 8-bit."""
        if sample > 32767:
            sample = 32767
        if sample < -32768:
            sample = -32768
        sign = 0x00
        if sample < 0:
            sample = -sample
            sign = 0x80
        if sample > 32635:
            sample = 32635
        if sample >= 2048:
            seg = 7
            for i in range(7):
                if sample <= (0x20 << i) * 16 - 1:
                    seg = i
                    break
            mant = (sample >> (seg + 3)) & 0x0F
            alaw = (seg << 4) | mant
        else:
            alaw = (sample >> 4) & 0x0F
        alaw ^= sign ^ 0x55
        return alaw & 0xFF

    @staticmethod
    def alaw2linear(a_val: int) -> int:
        """Converte PCMA 8-bit em PCM16 (signed)."""
        a_val ^= 0x55
        sign = a_val & 0x80
        seg = (a_val & 0x70) >> 4
        mant = a_val & 0x0F
        if seg == 0:
            sample = (mant << 4) + 8
        elif seg == 1:
            sample = (mant << 5) + 0x108
        else:
            sample = (mant << (seg + 3)) + (0x108 << (seg - 1))
        return -sample if sign else sample

    @staticmethod
    def pcm16_to_pcmu(buf: bytes) -> bytes:
        """Buffer PCM16LE -> PCMU."""
        out = bytearray()
        for i in range(0, len(buf), 2):
            sample = struct.unpack_from("<h", buf, i)[0]
            out.append(G711.linear2ulaw(sample))
        return bytes(out)

    @staticmethod
    def pcmu_to_pcm16(buf: bytes) -> bytes:
        """Buffer PCMU -> PCM16LE."""
        out = bytearray()
        for b in buf:
            s = G711.ulaw2linear(b)
            out += struct.pack("<h", s)
        return bytes(out)

    @staticmethod
    def pcm16_to_pcma(buf: bytes) -> bytes:
        """Buffer PCM16LE -> PCMA."""
        out = bytearray()
        for i in range(0, len(buf), 2):
            sample = struct.unpack_from("<h", buf, i)[0]
            out.append(G711.linear2alaw(sample))
        return bytes(out)

    @staticmethod
    def pcma_to_pcm16(buf: bytes) -> bytes:
        """Buffer PCMA -> PCM16LE."""
        out = bytearray()
        for b in buf:
            s = G711.alaw2linear(b)
            out += struct.pack("<h", s)
        return bytes(out)
