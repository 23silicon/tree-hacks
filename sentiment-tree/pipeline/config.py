from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    """Central configuration for the embedding pipeline."""

    # Embedding
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Relevance filtering
    relevance_threshold: float = 0.55

    # Sentiment scoring (zero-shot classification)
    sentiment_model: str = "facebook/bart-large-mnli"

    # NER / tagging
    spacy_model: str = "en_core_web_sm"
    topic_labels: list[str] = field(default_factory=lambda: [
        "economy", "technology", "politics", "finance", "crypto",
        "health", "energy", "environment", "regulation", "market",
    ])

    # Vector store
    chroma_persist_dir: str = str(Path("./chroma_data"))
    chroma_collection: str = "sentiment_tree"

    # Pipeline
    batch_size: int = 32

    # ─── Affinity pipeline (event → prediction scoring) ───────────

    # Stage 1: embedding candidate filter threshold
    affinity_embedding_threshold: float = 0.50

    # Stage 2: LLM scoring
    llm_provider: str = os.environ.get("SENTIMENT_TREE_LLM_PROVIDER", "anthropic")
    llm_model: str = os.environ.get("SENTIMENT_TREE_LLM_MODEL", "claude-sonnet-4-20250514")
    llm_base_url: str | None = os.environ.get("SENTIMENT_TREE_LLM_BASE_URL") or None
    llm_temperature: float = float(os.environ.get("SENTIMENT_TREE_LLM_TEMPERATURE", "0.1"))
