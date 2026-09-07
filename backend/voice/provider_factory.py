from functools import lru_cache

from backend.core.config import get_settings
from backend.voice.stt_base import STTProvider
from backend.voice.tts_base import TTSProvider


@lru_cache
def get_tts_provider() -> TTSProvider:
    settings = get_settings()
    if settings.tts_provider == "edge":
        from backend.voice.tts_edge import EdgeTTSProvider
        return EdgeTTSProvider()
    if settings.tts_provider == "openai":
        from backend.voice.tts_openai import OpenAITTSProvider
        return OpenAITTSProvider(api_key=settings.openai_api_key)
    if settings.tts_provider == "elevenlabs":
        from backend.voice.tts_elevenlabs import ElevenLabsTTSProvider
        return ElevenLabsTTSProvider(api_key=settings.elevenlabs_api_key)
    if settings.tts_provider == "local":
        from backend.voice.tts_local import LocalTTSProvider
        return LocalTTSProvider()
    raise NotImplementedError(f"TTS provider '{settings.tts_provider}' (local/custom) is not yet implemented.")


@lru_cache
def get_stt_provider() -> STTProvider:
    settings = get_settings()
    if settings.stt_provider == "whisper_local":
        from backend.voice.stt_whisper_local import WhisperLocalSTTProvider
        return WhisperLocalSTTProvider()
    if settings.stt_provider == "openai":
        from backend.voice.stt_openai import OpenAISTTProvider
        return OpenAISTTProvider(api_key=settings.openai_api_key)
    raise NotImplementedError(f"STT provider '{settings.stt_provider}' is not yet implemented.")
