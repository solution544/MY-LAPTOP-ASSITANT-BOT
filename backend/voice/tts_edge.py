"""
Microsoft Edge's neural TTS via the `edge-tts` library — free, no API key,
good quality. This is why TTS_PROVIDER=edge is the Phase 1/3 default: voice
output works immediately after `pip install -r requirements.txt`, with
ElevenLabs/OpenAI available as configuration upgrades, not requirements.
"""

import io

from backend.voice.tts_base import TTSProvider

DEFAULT_VOICE = "en-US-GuyNeural"


class EdgeTTSProvider(TTSProvider):
    def __init__(self, voice: str = DEFAULT_VOICE):
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        import edge_tts
        communicate = edge_tts.Communicate(text, self._voice)
        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        return buffer.getvalue()
