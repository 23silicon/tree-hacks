"""
Shared data models — all sources output these formats.
"""
from dataclasses import dataclass, asdict
from typing import Optional
import json


@dataclass
class Post:
    """Unified format for all text content (news articles, social posts, etc.)"""
    id: str
    source: str          # "google_news" | "bluesky" | "newsapi" | "twitter"
    author: str
    text: str
    timestamp: str       # ISO 8601
    url: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class MarketData:
    """Prediction market snapshot."""
    id: str
    question: str
    yes_price: float     # 0-1 probability
    no_price: float
    volume: float
    timestamp: str

    def to_dict(self):
        return asdict(self)


@dataclass
class Event:
    """A structured event extracted from posts — used for timeline building."""
    id: str
    title: str           # Short headline
    description: str     # 1-2 sentence summary
    date: str            # ISO date
    source_ids: list     # Post IDs this event was extracted from
    category: str        # "military", "diplomatic", "economic", "social", etc.
    impact: str          # "escalation", "de-escalation", "neutral"
    related_events: list # IDs of causally related events
    narratives: list     # Which narrative threads this belongs to

    def to_dict(self):
        return asdict(self)
