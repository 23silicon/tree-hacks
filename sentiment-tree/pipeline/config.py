from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    """Central configuration for the embedding pipeline."""

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"

    # Relevance filtering
    relevance_threshold: float = 0.25

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
