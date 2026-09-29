"""Query-time embedding for customer names, using the same model and prefix
convention as the SDN ingestion pipeline (`intfloat/multilingual-e5-small`,
"query: " prefix, L2-normalized) so cosine similarity between a customer name
and a sanctions name is meaningful. Loaded once per process.
"""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import get_settings


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model)


def embed_text(text: str) -> list[float]:
    if not text:
        return []
    model = _model()
    vector = model.encode(f"query: {text}", normalize_embeddings=True)
    return vector.tolist()
