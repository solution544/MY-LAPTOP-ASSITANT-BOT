"""
Embedding abstraction for semantic memory.

Uses a local sentence-transformers model by default.
The model is downloaded only when first needed and then cached locally.

If the local model cannot be loaded, the provider raises a clear error
instead of silently hanging the agent.
"""

import os
from functools import lru_cache

# Give Hugging Face much more time than its default 10-second timeout.
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "120")

from backend.core.config import get_settings


# Must match backend/database/models.py::Memory.embedding
EMBEDDING_DIM = 1536


class EmbeddingProvider:
    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Uses all-MiniLM-L6-v2.

    The model produces 384 dimensions. We zero-pad it to 1536 dimensions
    because the current PostgreSQL pgvector column expects 1536 dimensions.
    """

    MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                print(
                    f"[MEMORY] Loading embedding model: {self.MODEL_NAME}"
                )

                self._model = SentenceTransformer(self.MODEL_NAME)

                print(
                    "[MEMORY] Embedding model loaded successfully."
                )

            except Exception as exc:
                print(
                    f"[MEMORY] Failed to load embedding model: {exc}"
                )
                raise RuntimeError(
                    "The local memory embedding model could not be loaded. "
                    "Solution AI could not access the embedding model. "
                    "Check your internet connection and Hugging Face access."
                ) from exc

        return self._model

    async def embed(self, text: str) -> list[float]:
        model = self._load()

        vector = model.encode(
            text,
            normalize_embeddings=True,
        ).tolist()

        if len(vector) > EMBEDDING_DIM:
            raise ValueError(
                f"Embedding dimension {len(vector)} exceeds "
                f"configured dimension {EMBEDDING_DIM}."
            )

        return vector + [0.0] * (EMBEDDING_DIM - len(vector))


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when "
                "EMBEDDING_PROVIDER=openai"
            )

        import openai

        self._client = openai.AsyncOpenAI(
            api_key=api_key
        )

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )

        return response.data[0].embedding


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()

    provider = getattr(
        settings,
        "embedding_provider",
        "local",
    )

    if provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key
        )

    return LocalEmbeddingProvider()