from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import dagster as dg
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings


class DatabaseResource(dg.ConfigurableResource):
    """Sync SQLAlchemy session factory for Dagster ops (Dagster ops are sync)."""

    def _engine(self):
        return create_engine(get_settings().sync_database_url(), pool_pre_ping=True)

    @contextmanager
    def session(self) -> Iterator[Session]:
        engine = self._engine()
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class EmbeddingModelResource(dg.ConfigurableResource):
    """Loads the multilingual sentence-transformers model once per process."""

    model_name: str = "intfloat/multilingual-e5-small"

    def encode(self, texts: list[str], batch_size: int = 256) -> list[list[float]]:
        model = _load_model(self.model_name)
        prefixed = [f"query: {t}" for t in texts]
        embeddings = model.encode(
            prefixed,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()


@lru_cache(maxsize=4)
def _load_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


defs_resources = {
    "db": DatabaseResource(),
    "embedding_model": EmbeddingModelResource(model_name=get_settings().embedding_model),
}
