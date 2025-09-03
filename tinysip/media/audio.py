# audio.py
# PyAudio/WAV helpers for capture and playback (mono 16-bit, default 8 kHz)

import wave


def play_wav(filename: str) -> None:
    """Play a WAV file using PyAudio."""
    import pyaudio

    with wave.open(filename, "rb") as wf:
        p = pyaudio.PyAudio()
        stream = p.open(
            format=p.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
        )
        chunk = 1024
        data = wf.readframes(chunk)
        while data:
            stream.write(data)
            data = wf.readframes(chunk)
        stream.stop_stream()
        stream.close()
        p.terminate()


def record_wav(filename: str, seconds: int = 5, fs: int = 8000, channels: int = 1) -> None:
    """Record audio from default device and save as WAV."""
    import pyaudio

    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16, channels=channels, rate=fs, input=True, frames_per_buffer=1024
    )
    frames = []
    for _ in range(int(fs / 1024 * seconds)):
        frames.append(stream.read(1024))
    stream.stop_stream()
    stream.close()
    p.terminate()
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(b"".join(frames))


class AudioIO:
    """Simple wrapper for PyAudio input/output streams."""

    def __init__(self, fs: int = 8000, channels: int = 1):
        self.fs = fs
        self.channels = channels
        self.p = None
        self.in_stream = None
        self.out_stream = None

    def open(self, input_: bool = False, output: bool = False):
        import pyaudio

        self.p = pyaudio.PyAudio()
        if input_:
            self.in_stream = self.p.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.fs,
                input=True,
                frames_per_buffer=160,
            )
        if output:
            self.out_stream = self.p.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.fs,
                output=True,
                frames_per_buffer=160,
            )

    def read(self, n_frames: int = 160) -> bytes:
        if not self.in_stream:
            raise RuntimeError("Input stream not open")
        return self.in_stream.read(n_frames)

    def write(self, pcm16: bytes) -> None:
        if not self.out_stream:
            raise RuntimeError("Output stream not open")
        self.out_stream.write(pcm16)

    def close(self):
        if self.in_stream:
            self.in_stream.stop_stream()
            self.in_stream.close()
        if self.out_stream:
            self.out_stream.stop_stream()
            self.out_stream.close()
        if self.p:
            self.p.terminate()
            self.p = None
