"""Stage 1 — Embedding-based candidate filtering.

For every incoming event, compute cosine similarity against every
prediction market question.  Pairs below the threshold are discarded
as topically irrelevant — e.g. an article about Iran's film industry
vs. a prediction about US military strikes.

This stage is fast and cheap: just dot products on pre-computed vectors.
"""
from __future__ import annotations

import numpy as np

from .config import PipelineConfig
from .embedder import Embedder
from .models import Event, Prediction


class CandidateFilter:
    """Filter event-prediction pairs by embedding cosine similarity."""

    def __init__(
        self,
        embedder: Embedder,
        config: PipelineConfig | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.embedder = embedder

    def embed_events(self, events: list[Event]) -> list[Event]:
        """Compute and attach embeddings for events that don't have them."""
        needs_embedding = [e for e in events if e.embedding is None]
        if needs_embedding:
            texts = [e.full_text for e in needs_embedding]
            embeddings = self.embedder.embed_texts(texts)
            for event, emb in zip(needs_embedding, embeddings):
                event.embedding = emb
        return events

    def embed_predictions(self, predictions: list[Prediction]) -> list[Prediction]:
        """Compute and attach embeddings for predictions that don't have them."""
        needs_embedding = [p for p in predictions if p.embedding is None]
        if needs_embedding:
            texts = [p.question for p in needs_embedding]
            embeddings = self.embedder.embed_texts(texts)
            for pred, emb in zip(needs_embedding, embeddings):
                pred.embedding = emb
        return predictions

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine similarity between two vectors."""
        va, vb = np.array(a), np.array(b)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        if denom == 0:
            return 0.0
        return float(np.dot(va, vb) / denom)

    def score_pair(self, event: Event, prediction: Prediction) -> float:
        """Cosine similarity for a single event-prediction pair."""
        assert event.embedding is not None and prediction.embedding is not None
        return self.cosine_similarity(event.embedding, prediction.embedding)

    def filter_candidates(
        self,
        events: list[Event],
        predictions: list[Prediction],
    ) -> list[tuple[Event, Prediction, float]]:
        """Score all event×prediction pairs and keep those above threshold.

        Returns:
            List of (event, prediction, similarity_score) tuples that passed.
        """
        events = self.embed_events(events)
        predictions = self.embed_predictions(predictions)

        threshold = self.config.affinity_embedding_threshold
        candidates: list[tuple[Event, Prediction, float]] = []

        for event in events:
            for pred in predictions:
                sim = self.score_pair(event, pred)
                if sim >= threshold:
                    candidates.append((event, pred, sim))

        # Sort by similarity descending
        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates
