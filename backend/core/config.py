"""
Central application configuration.

Every configurable value in Solution AI is read from the environment
through this single Settings object.
"""

from functools import lru_cache
from typing import List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------------------------------------------------
    # Application
    # ---------------------------------------------------------
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    max_agent_steps: int = 30

    # Frontend URL used for production CORS.
    # Leave empty during local development.
    frontend_url: str = ""

    # ---------------------------------------------------------
    # Database
    # ---------------------------------------------------------
    database_url: str = (
        "postgresql+psycopg://solution_ai:changeme@localhost:5432/solution_ai"
    )

    # ---------------------------------------------------------
    # AI Providers
    # ---------------------------------------------------------
    ai_provider: Literal[
        "anthropic",
        "openai",
        "groq",
        "gemini",
        "local",
    ] = "openai"

    ai_model: str = "gpt-5.6-luna"
    groq_model: str = "openai/gpt-oss-120b"

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""

    # ---------------------------------------------------------
    # Web Search
    # ---------------------------------------------------------
    brave_api_key: str = ""

    # ---------------------------------------------------------
    # Memory Embeddings
    # ---------------------------------------------------------
    embedding_provider: Literal[
        "local",
        "openai",
    ] = "local"

    # ---------------------------------------------------------
    # Voice
    # ---------------------------------------------------------
    tts_provider: Literal[
        "openai",
        "elevenlabs",
        "edge",
        "local",
    ] = "edge"

    elevenlabs_api_key: str = ""

    stt_provider: Literal[
        "openai",
        "whisper_local",
    ] = "whisper_local"

    # ---------------------------------------------------------
    # Wake Word
    # ---------------------------------------------------------
    wake_word: str = "hey solution"
    wake_word_sensitivity: float = 0.5
    always_listening: bool = False

    # ---------------------------------------------------------
    # Security / Permissions
    # ---------------------------------------------------------
    allowed_folders: str = (
        r"C:\Users\HomePC\Desktop\solution-ai,"
        r"C:\Users\HomePC\Documents"
    )

    blocked_folders: str = ""

    confirmation_mode: Literal[
        "strict",
        "dangerous_only",
    ] = "strict"

    secret_key: str = ""

    # ---------------------------------------------------------
    # MCP Servers
    # ---------------------------------------------------------
    mcp_servers: str = "[]"

    # ---------------------------------------------------------
    # Helper Properties
    # ---------------------------------------------------------
    @property
    def allowed_folders_list(self) -> List[str]:
        return [
            path.strip()
            for path in self.allowed_folders.split(",")
            if path.strip()
        ]

    @property
    def blocked_folders_list(self) -> List[str]:
        return [
            path.strip()
            for path in self.blocked_folders.split(",")
            if path.strip()
        ]

    @property
    def active_provider_api_key(self) -> str:
        """Return the API key for the currently selected provider."""
        return {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "groq": self.groq_api_key,
            "gemini": self.gemini_api_key,
            "local": "",
        }.get(self.ai_provider, "")


@lru_cache
def get_settings() -> Settings:
    """
    Settings are read once and cached.

    Restart the backend after changing configuration.
    """
    return Settings()