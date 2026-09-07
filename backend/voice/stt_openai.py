import io

from backend.voice.stt_base import STTProvider


class OpenAISTTProvider(STTProvider):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when STT_PROVIDER=openai")
        import openai
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def transcribe(self, audio_bytes: bytes) -> str:
        buffer = io.BytesIO(audio_bytes)
        buffer.name = "audio.wav"
        response = await self._client.audio.transcriptions.create(model="whisper-1", file=buffer)
        return response.text
