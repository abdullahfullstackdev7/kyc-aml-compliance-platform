"""Query-time embedding for customer names, using the same model and prefix
convention as the SDN ingestion pipeline (`intfloat/multilingual-e5-small`,
"query: " prefix, L2-normalized) so cosine similarity between a customer name
and a sanctions name is meaningful. Loaded once per process.
"""

from __future__ import annotations

import threading

from backend.app.core.config import get_settings

_model_instance = None
_model_lock = threading.Lock()


def _model():
    # A plain @lru_cache is not a safe lazy-singleton under concurrency:
    # FastAPI runs sync endpoints in a thread pool, so on a cold process
    # several concurrent requests can all see the cache empty and each
    # start loading a full SentenceTransformer model in parallel - found by
    # running a Locust load test against a fresh process (PROJECT_PLAN.md
    # Phase 10.6), which crashed the server outright (a Rust allocator
    # abort from loading ~20 copies of the model at once, each also
    # hammering the HuggingFace Hub for cache-validation requests). The
    # double-checked lock below ensures only one thread ever constructs it.
    global _model_instance
    if _model_instance is None:
        with _model_lock:
            if _model_instance is None:
                from sentence_transformers import SentenceTransformer

                _model_instance = SentenceTransformer(get_settings().embedding_model)
    return _model_instance


def embed_text(text: str) -> list[float]:
    if not text:
        return []
    model = _model()
    vector = model.encode(f"query: {text}", normalize_embeddings=True)
    return vector.tolist()
