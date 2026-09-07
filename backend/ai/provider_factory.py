"""
AI provider factory.

OpenAI is the primary provider.
Groq is automatically used as a backup if OpenAI fails.
"""

from functools import lru_cache

from backend.ai.base import AIProvider
from backend.core.config import get_settings


@lru_cache
def get_ai_provider() -> AIProvider:
    settings = get_settings()

    # ---------------------------------------------------------
    # OpenAI PRIMARY + GROQ BACKUP
    # ---------------------------------------------------------

    if settings.ai_provider == "openai":
        from backend.ai.openai_provider import OpenAIProvider
        from backend.ai.groq_provider import GroqProvider
        from backend.ai.fallback_provider import FallbackAIProvider

        openai_provider = OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.ai_model,
        )

        groq_provider = GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
        )

        return FallbackAIProvider(
            primary=openai_provider,
            backup=groq_provider,
        )

    # ---------------------------------------------------------
    # GROQ ONLY
    # ---------------------------------------------------------

    if settings.ai_provider == "groq":
        from backend.ai.groq_provider import GroqProvider

        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
        )

    # ---------------------------------------------------------
    # ANTHROPIC
    # ---------------------------------------------------------

    if settings.ai_provider == "anthropic":
        from backend.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.ai_model,
        )

    # ---------------------------------------------------------
    # GEMINI
    # ---------------------------------------------------------

    if settings.ai_provider == "gemini":
        raise NotImplementedError(
            "GeminiProvider is planned but not yet implemented."
        )

    # ---------------------------------------------------------
    # LOCAL
    # ---------------------------------------------------------

    if settings.ai_provider == "local":
        raise NotImplementedError(
            "LocalModelProvider is planned but not yet implemented."
        )

    raise ValueError(
        f"Unknown AI_PROVIDER: {settings.ai_provider}"
    )