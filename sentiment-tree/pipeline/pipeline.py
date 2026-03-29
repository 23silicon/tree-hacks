from __future__ import annotations

from .config import PipelineConfig
from .embedder import Embedder
from .models import EnrichedItem, RawItem
from .relevance_filter import RelevanceFilter
from .sentiment_scorer import SentimentScorer
from .tagger import Tagger
from .vector_store import VectorStore


class Pipeline:
    """Orchestrates the full embedding pipeline: embed → filter → score → tag → store."""

    def __init__(
        self,
        contract_question: str,
        config: PipelineConfig | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.contract_question = contract_question

        # Initialize components (lazy-loaded internally)
        self.embedder = Embedder(self.config)
        self.relevance_filter = RelevanceFilter(contract_question, self.embedder, self.config)
        self.sentiment_scorer = SentimentScorer(contract_question, self.config)
        self.tagger = Tagger(self.config)
        self.vector_store = VectorStore(self.config)

    def process(
        self,
        items: list[RawItem],
        store: bool = True,
    ) -> list[EnrichedItem]:
        """Run all pipeline stages on a batch of raw items.

        Args:
            items: Raw scraped items from Role 1.
            store: Whether to persist enriched items to the vector store.

        Returns:
            List of enriched items that passed relevance filtering.
        """
        if not items:
            return []

        texts = [item.text for item in items]

        # 1. Embed
        embeddings = self.embedder.embed_texts(texts)

        # 2. Relevance filter
        relevance_scores = self.relevance_filter.score_batch(embeddings)
        relevant_indices = [
            i for i, score in enumerate(relevance_scores)
            if self.relevance_filter.is_relevant(score)
        ]

        if not relevant_indices:
            return []

        relevant_items = [items[i] for i in relevant_indices]
        relevant_texts = [texts[i] for i in relevant_indices]
        relevant_embeddings = [embeddings[i] for i in relevant_indices]
        relevant_scores = [relevance_scores[i] for i in relevant_indices]

        # 3. Sentiment scoring (only on relevant items)
        sentiment_results = self.sentiment_scorer.score_batch(relevant_texts)

        # 4. Tagging (only on relevant items)
        tag_results = self.tagger.tag_batch(relevant_texts)

        # 5. Assemble enriched items
        enriched: list[EnrichedItem] = []
        for i, item in enumerate(relevant_items):
            sentiment_score, sentiment_confidence = sentiment_results[i]
            entities, topic_tags = tag_results[i]

            enriched.append(EnrichedItem(
                text=item.text,
                source=item.source,
                timestamp=item.timestamp,
                url=item.url,
                embedding=relevant_embeddings[i],
                sentiment_score=round(sentiment_score, 4),
                sentiment_confidence=round(sentiment_confidence, 4),
                topic_tags=topic_tags,
                entities=entities,
                relevance_score=round(relevant_scores[i], 4),
            ))

        # 6. Store
        if store and enriched:
            self.vector_store.add(enriched)

        return enriched

    def process_single(self, item: RawItem, store: bool = True) -> EnrichedItem | None:
        """Convenience method for processing a single item."""
        results = self.process([item], store=store)
        return results[0] if results else None
