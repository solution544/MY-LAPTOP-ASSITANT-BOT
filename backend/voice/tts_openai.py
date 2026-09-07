from backend.voice.tts_base import TTSProvider


class OpenAITTSProvider(TTSProvider):
    def __init__(self, api_key: str, voice: str = "alloy"):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when TTS_PROVIDER=openai")
        import openai
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        response = await self._client.audio.speech.create(model="tts-1", voice=self._voice, input=text)
        return response.content
