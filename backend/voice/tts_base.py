"""Text-to-speech abstraction (spec section 9) — same pattern as AIProvider."""

from abc import ABC, abstractmethod


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Return audio bytes (MP3) for the given text."""
        raise NotImplementedError
