# dtmf.py
# In-band DTMF tone generation (PCM 16-bit, 8 kHz default)

import math
import struct

DTMF_FREQS: dict[str, tuple[int, int]] = {
    "1": (697, 1209),
    "2": (697, 1336),
    "3": (697, 1477),
    "A": (697, 1633),
    "4": (770, 1209),
    "5": (770, 1336),
    "6": (770, 1477),
    "B": (770, 1633),
    "7": (852, 1209),
    "8": (852, 1336),
    "9": (852, 1477),
    "C": (852, 1633),
    "*": (941, 1209),
    "0": (941, 1336),
    "#": (941, 1477),
    "D": (941, 1633),
}


def generate_dtmf_tone(
    digit: str, duration_ms: int = 100, fs: int = 8000, amplitude: int = 14000, ramp_ms: int = 5
) -> bytes:
    """Generate a PCM 16-bit mono buffer with the DTMF tone of the given digit."""
    digit = digit.upper()
    if digit not in DTMF_FREQS:
        raise ValueError(f"Invalid DTMF digit: {digit}")
    f_low, f_high = DTMF_FREQS[digit]
    n_samples = int(fs * duration_ms / 1000)
    n_ramp = max(1, int(fs * ramp_ms / 1000))
    buf = bytearray()
    for n in range(n_samples):
        t = n / fs
        # simple linear attack/decay ramp
        if n < n_ramp:
            gain = n / n_ramp
        elif n > n_samples - n_ramp:
            gain = (n_samples - n) / n_ramp
        else:
            gain = 1.0
        s = (
            gain
            * 0.5
            * (math.sin(2.0 * math.pi * f_low * t) + math.sin(2.0 * math.pi * f_high * t))
        )
        val = int(max(-1.0, min(1.0, s)) * amplitude)
        buf += struct.pack("<h", val)
    return bytes(buf)


def sequence_to_pcm(digits: str, tone_ms: int = 100, pause_ms: int = 50, fs: int = 8000) -> bytes:
    """Encode a sequence of digits into PCM16 with pauses between tones."""
    pcm = bytearray()
    pause = b"\x00\x00" * int(fs * pause_ms / 1000)
    for d in digits:
        if d.strip() == "":
            continue
        pcm += generate_dtmf_tone(d, tone_ms, fs)
        pcm += pause
    return bytes(pcm)


def save_wav(filename: str, pcm16: bytes, fs: int = 8000) -> None:
    """Save PCM16 mono as a WAV file."""
    import wave

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(pcm16)


def play_pyaudio(pcm16: bytes, fs: int = 8000) -> None:
    """Play PCM16 mono via PyAudio (if available)."""
    try:
        import pyaudio
    except ImportError as e:
        raise RuntimeError("PyAudio not installed") from e

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=fs, output=True)
    stream.write(pcm16)
    stream.stop_stream()
    stream.close()
    p.terminate()
