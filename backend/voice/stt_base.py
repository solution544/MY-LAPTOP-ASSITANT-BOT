"""Speech-to-text abstraction (spec section 8)."""

from abc import ABC, abstractmethod


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Return transcribed text from audio bytes (WAV/MP3)."""
        raise NotImplementedError
