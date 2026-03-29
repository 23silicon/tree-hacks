from __future__ import annotations

import numpy as np

from .config import PipelineConfig
from .embedder import Embedder


class RelevanceFilter:
    """Scores items against a contract question and filters by relevance."""

    def __init__(
        self,
        contract_question: str,
        embedder: Embedder,
        config: PipelineConfig | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.embedder = embedder
        self.contract_question = contract_question
        self._question_embedding: list[float] | None = None

    @property
    def question_embedding(self) -> list[float]:
        if self._question_embedding is None:
            self._question_embedding = self.embedder.embed_single(self.contract_question)
        return self._question_embedding

    def score(self, embedding: list[float]) -> float:
        """Cosine similarity between an item embedding and the contract question."""
        a = np.array(embedding)
        b = np.array(self.question_embedding)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def score_batch(self, embeddings: list[list[float]]) -> list[float]:
        """Score a batch of embeddings against the contract question."""
        return [self.score(emb) for emb in embeddings]

    def is_relevant(self, relevance_score: float) -> bool:
        """Check if a score exceeds the configured threshold."""
        return relevance_score >= self.config.relevance_threshold
