from __future__ import annotations

from typing import Any

from .config import PipelineConfig
from .embedder import Embedder
from .vector_store import VectorStore


class SemanticSearch:
    """User-facing semantic search over the vector store."""

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        config: PipelineConfig | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.embedder = embedder
        self.vector_store = vector_store

    def search(
        self,
        query: str,
        n_results: int = 10,
        source_filter: str | None = None,
        min_sentiment: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search the vector store with a natural language query.

        Args:
            query: Free-text search query.
            n_results: Number of results to return.
            source_filter: Optional platform filter (e.g. "reddit").
            min_sentiment: Optional minimum sentiment score filter.

        Returns:
            List of result dicts with text, metadata, and distance.
        """
        query_embedding = self.embedder.embed_single(query)

        where: dict[str, Any] | None = None
        if source_filter:
            where = {"source": source_filter}

        raw = self.vector_store.query(
            query_embedding=query_embedding,
            n_results=n_results,
            where=where,
        )

        results: list[dict[str, Any]] = []
        if not raw["documents"] or not raw["documents"][0]:
            return results

        for i, doc in enumerate(raw["documents"][0]):
            meta = raw["metadatas"][0][i] if raw["metadatas"] else {}
            distance = raw["distances"][0][i] if raw["distances"] else None

            # Apply post-query sentiment filter
            if min_sentiment is not None:
                item_sentiment = meta.get("sentiment_score", 0)
                if item_sentiment < min_sentiment:
                    continue

            results.append({
                "text": doc,
                "distance": distance,
                "similarity": 1.0 - distance if distance is not None else None,
                **meta,
            })

        return results
