import asyncio
import os
import tempfile
import pyttsx3

from backend.voice.tts_base import TTSProvider


class LocalTTSProvider(TTSProvider):
    def __init__(self, voice=None, rate=175):
        self._voice = voice
        self._rate = rate

    async def synthesize(self, text: str) -> bytes:
        return await asyncio.to_thread(self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> bytes:
        tmp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False,
            ) as tmp:
                tmp_path = tmp.name

            engine = pyttsx3.init()

            engine.setProperty("rate", self._rate)

            if self._voice:
                engine.setProperty("voice", self._voice)

            engine.save_to_file(text, tmp_path)
            engine.runAndWait()
            engine.stop()

            with open(tmp_path, "rb") as f:
                return f.read()

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except PermissionError:
                    pass