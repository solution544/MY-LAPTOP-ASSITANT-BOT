"""
Embedding abstraction for semantic memory (spec section 18/7).

Anthropic doesn't currently offer an embeddings endpoint, so this is
intentionally separate from `backend/ai/` — a user can be on
AI_PROVIDER=anthropic for chat while embeddings come from a different,
smaller model. Default is a local sentence-transformers model (no API key,
no per-call cost, works offline) so memory works out of the box; set
EMBEDDING_PROVIDER=openai to use OpenAI's embeddings API instead if you'd
rather not download a local model.
"""

from functools import lru_cache

from backend.core.config import get_settings

EMBEDDING_DIM = 1536  # must match backend/database/models.py::Memory.embedding


class EmbeddingProvider:
    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Uses sentence-transformers (all-MiniLM-L6-v2, 384-dim) and zero-pads to
    EMBEDDING_DIM so it fits the same pgvector column regardless of which
    provider generated it. Downloaded once on first use (~90MB), then cached
    locally — no network needed after that.
    """

    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model

    async def embed(self, text: str) -> list[float]:
        model = self._load()
        vector = model.encode(text).tolist()
        return vector + [0.0] * (EMBEDDING_DIM - len(vector))


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        import openai
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(model="text-embedding-3-small", input=text)
        return response.data[0].embedding


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    provider = getattr(settings, "embedding_provider", "local")
    if provider == "openai":
        return OpenAIEmbeddingProvider(api_key=settings.openai_api_key)
    return LocalEmbeddingProvider()
