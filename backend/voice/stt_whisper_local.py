
"""
Local speech-to-text via faster-whisper.

Uses faster-whisper with CPU/int8 by default so speech recognition
can run locally without an API key.

The frontend records browser audio as WebM/Opus. We save the incoming
audio to a temporary .webm file, close it before faster-whisper reads it,
then remove the file after transcription.
"""

import os
import tempfile

from backend.voice.stt_base import STTProvider


class WhisperLocalSTTProvider(STTProvider):
    def __init__(self, model_size: str = "base"):
        self._model_size = model_size
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_size,
                device="cpu",
                compute_type="int8",
            )

        return self._model

    async def transcribe(self, audio_bytes: bytes) -> str:
        model = self._load()

        # Windows does not allow another process/library to open a
        # NamedTemporaryFile while it is still open. Therefore:
        # 1. Create the temporary file.
        # 2. Write the audio.
        # 3. Close the file.
        # 4. Let faster-whisper open it.
        # 5. Delete it afterward.

        tmp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                suffix=".webm",
                delete=False,
            ) as tmp:
                tmp.write(audio_bytes)
                tmp.flush()
                tmp_path = tmp.name

            segments, _info = model.transcribe(tmp_path)

            transcript = " ".join(
                segment.text.strip()
                for segment in segments
                if segment.text.strip()
            )

            return transcript.strip()

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except PermissionError:
                    pass

