from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class RawItem(BaseModel):
    """Input schema from Role 1 (data scraping)."""

    text: str
    source: str  # e.g. "reddit", "x", "news_rss", "youtube"
    timestamp: datetime
    url: str


class EnrichedItem(BaseModel):
    """Output schema to Role 3 (branching / clustering)."""

    # Preserved from RawItem
    text: str
    source: str
    timestamp: datetime
    url: str

    # Added by embedding pipeline
    embedding: list[float]
    sentiment_score: float = Field(
        ge=-1.0, le=1.0,
        description="Directional sentiment relative to contract outcome (-1=no, 1=yes)",
    )
    sentiment_confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the sentiment score",
    )
    topic_tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    relevance_score: float = Field(
        ge=0.0, le=1.0,
        description="Cosine similarity to the contract's core question",
    )
