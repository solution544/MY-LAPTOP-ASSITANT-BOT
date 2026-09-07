import httpx

from backend.voice.tts_base import TTSProvider

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs' default "Rachel" voice


class ElevenLabsTTSProvider(TTSProvider):
    def __init__(self, api_key: str, voice_id: str = DEFAULT_VOICE_ID):
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is required when TTS_PROVIDER=elevenlabs")
        self._api_key = api_key
        self._voice_id = voice_id

    async def synthesize(self, text: str) -> bytes:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self._voice_id}",
                headers={"xi-api-key": self._api_key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_monolingual_v1"},
            )
            response.raise_for_status()
            return response.content
