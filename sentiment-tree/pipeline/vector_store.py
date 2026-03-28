from __future__ import annotations

import uuid
from typing import Any

import chromadb
from chromadb.config import Settings

from .config import PipelineConfig
from .models import EnrichedItem


class VectorStore:
    """ChromaDB-backed vector storage for enriched items."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    @property
    def client(self) -> chromadb.ClientAPI:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self.config.chroma_persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    @property
    def collection(self) -> chromadb.Collection:
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.config.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add(self, items: list[EnrichedItem]) -> list[str]:
        """Store enriched items. Returns assigned IDs."""
        if not items:
            return []

        ids = [str(uuid.uuid4()) for _ in items]
        documents = [item.text for item in items]
        embeddings = [item.embedding for item in items]
        metadatas: list[dict[str, Any]] = [
            {
                "source": item.source,
                "timestamp": item.timestamp.isoformat(),
                "url": item.url,
                "sentiment_score": item.sentiment_score,
                "sentiment_confidence": item.sentiment_confidence,
                "relevance_score": item.relevance_score,
                "topic_tags": ",".join(item.topic_tags),
                "entities": ",".join(item.entities),
            }
            for item in items
        ]

        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return ids

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query by embedding vector. Returns ChromaDB result dict."""
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances", "embeddings"],
        }
        if where:
            kwargs["where"] = where
        return self.collection.query(**kwargs)

    def count(self) -> int:
        """Return total items in the collection."""
        return self.collection.count()

    def reset(self) -> None:
        """Delete and recreate the collection."""
        self.client.delete_collection(self.config.chroma_collection)
        self._collection = None
