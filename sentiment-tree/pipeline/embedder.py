from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from .config import PipelineConfig


class Embedder:
    """Generates vector embeddings for raw text items."""

    _MODEL_CACHE: dict[str, SentenceTransformer] = {}

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            model_name = self.config.embedding_model
            if model_name not in self._MODEL_CACHE:
                self._MODEL_CACHE[model_name] = SentenceTransformer(model_name)
            self._model = self._MODEL_CACHE[model_name]
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of embedding vectors."""
        embeddings: np.ndarray = self.model.encode(
            texts,
            batch_size=self.config.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.tolist()

    def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        return self.embed_texts([text])[0]
