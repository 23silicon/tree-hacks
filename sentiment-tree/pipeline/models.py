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


# ─── New models for event → prediction affinity pipeline ─────────────


class EventSource(BaseModel):
    """A single source backing an event."""
    Source: str
    Link: str
    Summary: str


class Event(BaseModel):
    """Incoming live event from the events stream."""
    Title: str
    Description: str
    Sources: list[EventSource] = Field(default_factory=list)
    ID: int
    embedding: list[float] | None = None

    @property
    def full_text(self) -> str:
        """Combine title + description + source summaries into one text block."""
        parts = [self.Title, self.Description]
        for s in self.Sources:
            if s.Summary:
                parts.append(s.Summary)
        return ". ".join(parts)


class Prediction(BaseModel):
    """A prediction market contract (Polymarket / Kalshi)."""
    id: str
    source: str  # "polymarket" or "kalshi"
    question: str
    category: str
    yes_probability: float
    no_probability: float
    volume_usd: float
    liquidity_usd: float
    closes_at: datetime
    url: str
    embedding: list[float] | None = None


class AffinityResult(BaseModel):
    """Output of the two-stage affinity pipeline for one event-prediction pair."""
    event_id: int
    prediction_id: str
    event_title: str
    prediction_question: str

    # Stage 1: embedding similarity
    embedding_similarity: float = Field(
        description="Cosine similarity from Stage 1 candidate filtering",
    )

    # Stage 2: LLM affinity scoring
    direction: float = Field(
        ge=-1.0, le=1.0,
        description="How this event shifts the prediction: -1 (toward NO) to +1 (toward YES)",
    )
    magnitude: float = Field(
        ge=0.0, le=1.0,
        description="Strength of the evidential link (0 = weak, 1 = strong)",
    )
    reasoning: str = Field(
        description="LLM-generated explanation of why this event affects this prediction",
    )
