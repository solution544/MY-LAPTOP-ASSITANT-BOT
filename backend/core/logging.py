"""
Application logging.

Per the project spec (section 34), Solution AI logs application events, AI
requests, tool calls, and errors — but must NEVER log API keys, passwords,
tokens, or other credentials. `redact()` is applied to any dict that might
contain such fields before it is logged.
"""

import logging
import logging.handlers
import os
from pathlib import Path

_SENSITIVE_KEYS = {
    "api_key", "apikey", "password", "token", "authorization",
    "secret", "secret_key", "anthropic_api_key", "openai_api_key",
    "gemini_api_key", "elevenlabs_api_key",
}


def redact(data: dict) -> dict:
    """Return a copy of `data` with sensitive values replaced by '***REDACTED***'."""
    redacted = {}
    for key, value in data.items():
        if key.lower() in _SENSITIVE_KEYS:
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = redact(value)
        else:
            redacted[key] = value
    return redacted


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger("solution_ai")
    logger.setLevel(log_level)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "solution_ai.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
