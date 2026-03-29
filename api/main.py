from __future__ import annotations

import asyncio
import hashlib
import html
import json
import math
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_SOURCING_DIR = PROJECT_ROOT / "data-sourcing"
SENTIMENT_TREE_DIR = PROJECT_ROOT / "sentiment-tree"
load_dotenv(PROJECT_ROOT / ".env")

for path in (DATA_SOURCING_DIR, SENTIMENT_TREE_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

try:
    import google_news as data_google_news  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - optional dependency surface
    data_google_news = None
    GOOGLE_NEWS_IMPORT_ERROR = str(exc)
else:
    GOOGLE_NEWS_IMPORT_ERROR = None

try:
    import bluesky_stream as data_bluesky_stream  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - optional dependency surface
    data_bluesky_stream = None
    BLUESKY_IMPORT_ERROR = str(exc)
else:
    BLUESKY_IMPORT_ERROR = None


GAMMA_PUBLIC_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
KALSHI_MARKETS_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"
HACKERNEWS_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "8.0"))
SAMPLE_DATA_PATH = PROJECT_ROOT / "sentiment-tree" / "polymarket_preds.json"
CACHE_DB_PATH = PROJECT_ROOT / "api" / "source_cache.sqlite3"
DEFAULT_WORKFLOW_PREDICTION_LIMIT = 24
DEFAULT_WORKFLOW_DESCENDANTS = 24
MAX_WORKFLOW_DESCENDANTS = 40
DEFAULT_LIVE_POLL_INTERVAL_SECONDS = 12
LIVE_POLL_MIN_SECONDS = 5
LIVE_POLL_MAX_SECONDS = 60
POLYMARKET_PAGE_SIZE = int(os.environ.get("POLYMARKET_PAGE_SIZE", "300"))
POLYMARKET_MAX_PAGES = int(os.environ.get("POLYMARKET_MAX_PAGES", "1"))
KALSHI_PAGE_SIZE = int(os.environ.get("KALSHI_PAGE_SIZE", "300"))
KALSHI_MAX_PAGES = int(os.environ.get("KALSHI_MAX_PAGES", "1"))
POLYMARKET_PUBLIC_SEARCH_TERMS = int(os.environ.get("POLYMARKET_PUBLIC_SEARCH_TERMS", "3"))
POLYMARKET_PUBLIC_SEARCH_LIMIT = int(os.environ.get("POLYMARKET_PUBLIC_SEARCH_LIMIT", "10"))
NEWS_RESULTS_PER_TERM = 80
NEWS_TERM_LIMIT = 5
HACKERNEWS_RESULTS_PER_TERM = 20
HACKERNEWS_TERM_LIMIT = 4
RSS_RESULTS_PER_FEED = int(os.environ.get("RSS_RESULTS_PER_FEED", "8"))
RSS_FEED_LIMIT = int(os.environ.get("RSS_FEED_LIMIT", "18"))
REDDIT_RESULTS_PER_QUERY = int(os.environ.get("REDDIT_RESULTS_PER_QUERY", "36"))
PRELOAD_SENTIMENT_TREE_MODELS = os.environ.get("PRELOAD_SENTIMENT_TREE_MODELS", "1") != "0"
DEFAULT_RUN_LLM_AFFINITY = os.environ.get("DEFAULT_RUN_LLM_AFFINITY")
if DEFAULT_RUN_LLM_AFFINITY is None:
    DEFAULT_RUN_LLM_AFFINITY = "1" if (
        os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    ) else "0"
DEFAULT_RUN_LLM_AFFINITY = DEFAULT_RUN_LLM_AFFINITY != "0"
PREDICTION_MIN_EMBEDDING_SIM = float(os.environ.get("PREDICTION_MIN_EMBEDDING_SIM", "0.34"))
PREDICTION_MIN_SCORE = float(os.environ.get("PREDICTION_MIN_SCORE", "18"))
PREDICTION_MIN_POPULARITY_FLOOR = float(os.environ.get("PREDICTION_MIN_POPULARITY_FLOOR", "0.18"))
EVENT_MIN_RELEVANCE_SCORE = float(os.environ.get("EVENT_MIN_RELEVANCE_SCORE", "0.36"))
AFFINITY_LLM_MAX_CANDIDATES = int(os.environ.get("AFFINITY_LLM_MAX_CANDIDATES", "8"))
MAX_ANALYSIS_POSTS = int(os.environ.get("MAX_ANALYSIS_POSTS", "80"))
EVENT_CLUSTER_WINDOW_HOURS = int(os.environ.get("EVENT_CLUSTER_WINDOW_HOURS", "72"))
EVENT_CLUSTER_MIN_MERGE_SCORE = float(os.environ.get("EVENT_CLUSTER_MIN_MERGE_SCORE", "5"))
CACHED_POST_LOOKBACK_DAYS = int(os.environ.get("CACHED_POST_LOOKBACK_DAYS", "365"))
CACHED_POST_LIMIT = int(os.environ.get("CACHED_POST_LIMIT", "180"))
QUERY_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "the", "to", "what", "when", "where",
    "will", "with",
}
WEAK_QUERY_TOKENS = {
    "beat",
    "beating",
    "latest",
    "market",
    "markets",
    "odds",
    "price",
    "prices",
    "today",
    "win",
    "winning",
    "wins",
}

TEXT_EMBEDDING_CACHE: dict[str, list[float]] = {}
TEXT_EMBEDDER: Any | None = None
TEXT_EMBEDDER_ERROR: str | None = None
LLM_AFFINITY_CACHE: dict[str, dict[str, Any]] = {}

RSS_FEEDS: dict[str, str] = {
    "Reuters World": "https://feeds.reuters.com/Reuters/worldNews",
    "AP News": "https://rsshub.app/apnews/topics/world-news",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "NPR News": "https://feeds.npr.org/1001/rss.xml",
    "WSJ World": "https://feeds.content.dowjones.io/public/rss/RSSWorldNews.xml",
    "Fox News World": "https://moxie.foxnews.com/google-publisher/world.xml",
    "CBS News": "https://www.cbsnews.com/latest/rss/world",
    "ABC News": "https://abcnews.go.com/abcnews/internationalheadlines",
    "The Hill": "https://thehill.com/feed/",
    "Guardian World": "https://www.theguardian.com/world/rss",
    "CNN Top": "http://rss.cnn.com/rss/edition.rss",
    "NBC News": "https://feeds.nbcnews.com/nbcnews/public/news",
    "Politico": "https://rss.politico.com/politics-news.xml",
    "Axios": "https://api.axios.com/feed/",
    "Business Insider": "https://www.businessinsider.com/rss",
    "Yahoo News": "https://news.yahoo.com/rss/",
    "MarketWatch": "http://feeds.marketwatch.com/marketwatch/topstories/",
}

REDDIT_HEADERS = {
    "User-Agent": "tree-hacks-bot/0.2",
    "Accept": "application/json",
}


app = FastAPI(
    title="Tree Hacks API",
    version="0.2.0",
    description=(
        "Unified backend for sourcing data, searching Polymarket, running the "
        "sentiment-tree bridge when available, and returning graph-ready payloads "
        "for the frontend."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def preload_models_on_startup() -> None:
    init_source_cache()
    app.state.startup_warnings = []
    if not PRELOAD_SENTIMENT_TREE_MODELS:
        return

    warnings = await asyncio.to_thread(warm_sentiment_tree_models)
    app.state.startup_warnings = warnings
    if warnings:
        for warning in warnings:
            print(f"[startup] {warning}")
    else:
        print("[startup] sentiment-tree models preloaded")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Question, topic, or event")
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    include_closed: bool = Field(
        False, description="Whether to include closed markets from the upstream feed"
    )


class WorkflowRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Topic or question to investigate")
    prediction_limit: int = Field(DEFAULT_WORKFLOW_PREDICTION_LIMIT, ge=1, le=MAX_LIMIT)
    include_closed: bool = False
    include_social: bool = True
    bluesky_seconds: int = Field(3, ge=0, le=20)
    max_descendants: int = Field(DEFAULT_WORKFLOW_DESCENDANTS, ge=1, le=MAX_WORKFLOW_DESCENDANTS)
    relevance_threshold: float = Field(0.55, ge=0.0, le=1.0)
    affinity_threshold: float = Field(0.50, ge=0.0, le=1.0)
    run_llm_affinity: bool = DEFAULT_RUN_LLM_AFFINITY


class LiveWorkflowRequest(WorkflowRequest):
    poll_interval_seconds: int = Field(
        DEFAULT_LIVE_POLL_INTERVAL_SECONDS,
        ge=LIVE_POLL_MIN_SECONDS,
        le=LIVE_POLL_MAX_SECONDS,
    )


class Prediction(BaseModel):
    id: str
    source: str
    question: str
    category: str | None = None
    context: str | None = None
    yes_probability: float | None = None
    no_probability: float | None = None
    volume_usd: float | None = None
    liquidity_usd: float | None = None
    closes_at: str | None = None
    url: str | None = None
    relevance_score: float | None = None


class SourcedPost(BaseModel):
    id: str
    source: str
    author: str = ""
    text: str
    timestamp: str
    url: str | None = None
    recency_tag: str | None = None


class WorkflowEvent(BaseModel):
    id: str
    title: str
    description: str
    source: str
    timestamp: str
    url: str | None = None
    source_count: int = 0
    sources: list[dict[str, Any]] = Field(default_factory=list)
    stack_key: str | None = None
    support_prediction_ids: list[str] = Field(default_factory=list)
    sentiment_score: float | None = None
    relevance_score: float | None = None
    topic_tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    time_scope: str | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def snapshot_token() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_cache_connection() -> sqlite3.Connection:
    CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(CACHE_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_source_cache() -> None:
    with get_cache_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cached_posts (
                cache_key TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                source TEXT NOT NULL,
                author TEXT NOT NULL,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                url TEXT,
                recency_tag TEXT,
                query TEXT,
                collected_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_cached_posts_timestamp ON cached_posts(timestamp DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_cached_posts_query ON cached_posts(query)"
        )


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = parsedate_to_datetime(raw)
            except (TypeError, ValueError):
                return datetime.now(timezone.utc)
    else:
        return datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_timestamp(value: Any) -> str:
    return parse_datetime(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def classify_recency_tag(value: Any) -> str:
    age_seconds = max(
        0.0,
        (datetime.now(timezone.utc) - parse_datetime(value)).total_seconds(),
    )
    age_days = age_seconds / 86400
    if age_days <= 2:
        return "breaking"
    if age_days <= 14:
        return "recent"
    if age_days <= 90:
        return "context"
    return "historical"


def tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token}


def cosine_similarity(
    left: list[float] | None,
    right: list[float] | None,
) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def get_text_embedder() -> Any | None:
    global TEXT_EMBEDDER, TEXT_EMBEDDER_ERROR

    if TEXT_EMBEDDER is not None:
        return TEXT_EMBEDDER
    if TEXT_EMBEDDER_ERROR is not None:
        return None

    try:
        from pipeline.config import PipelineConfig
        from pipeline.embedder import Embedder

        TEXT_EMBEDDER = Embedder(PipelineConfig())
    except Exception as exc:
        TEXT_EMBEDDER_ERROR = str(exc)
        return None

    return TEXT_EMBEDDER


def embed_text_value(text: str) -> list[float] | None:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if not normalized:
        return None

    cached = TEXT_EMBEDDING_CACHE.get(normalized)
    if cached is not None:
        return cached

    embedder = get_text_embedder()
    if embedder is None:
        return None

    try:
        embedding = embedder.embed_single(normalized)
    except Exception as exc:
        global TEXT_EMBEDDER_ERROR
        TEXT_EMBEDDER_ERROR = str(exc)
        return None

    TEXT_EMBEDDING_CACHE[normalized] = embedding
    return embedding


def semantic_text_similarity(left: str, right: str) -> float:
    return cosine_similarity(embed_text_value(left), embed_text_value(right))


def clamp_probability(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number > 1:
        return round(number / 100, 4)
    if number < 0:
        return None
    return round(number, 4)


def normalize_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_possible_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def coerce_text_list(value: Any) -> list[str]:
    return [str(item) for item in parse_possible_json_list(value)]


def coerce_number_list(value: Any) -> list[float]:
    numbers: list[float] = []
    for item in parse_possible_json_list(value):
        try:
            numbers.append(float(item))
        except (TypeError, ValueError):
            continue
    return numbers


def extract_query_terms(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    if not normalized:
        return []

    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if token not in QUERY_STOP_WORDS and len(token) > 2
    ]
    terms: list[str] = []
    seen: set[str] = set()

    def add_term(value: str) -> None:
        clean = re.sub(r"\s+", " ", value).strip().lower()
        if not clean or clean in seen:
            return
        seen.add(clean)
        terms.append(clean)

    add_term(normalized)

    for token in tokens[:6]:
        add_term(token)

    for index in range(len(tokens) - 1):
        add_term(f"{tokens[index]} {tokens[index + 1]}")

    return terms


def build_market_search_terms(query: str, posts: list[SourcedPost] | None = None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add_term(value: str) -> None:
        clean = re.sub(r"\s+", " ", value).strip().lower()
        if not clean or clean in seen:
            return
        seen.add(clean)
        terms.append(clean)

    for term in extract_query_terms(query):
        add_term(term)

    if posts:
        counts: dict[str, int] = defaultdict(int)
        for post in posts[:20]:
            for term in extract_query_terms(post.text):
                if len(term) >= 4:
                    counts[term] += 1

        ranked_terms = sorted(
            counts.items(),
            key=lambda item: (-item[1], len(item[0])),
        )
        for term, _ in ranked_terms[:8]:
            add_term(term)

    return terms[:10]


def build_news_search_terms(query: str, posts: list[SourcedPost] | None = None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add_term(value: str) -> None:
        clean = re.sub(r"\s+", " ", value).strip().lower()
        if not clean or clean in seen:
            return
        seen.add(clean)
        terms.append(clean)

    add_term(query)
    for term in extract_query_terms(query):
        add_term(term)

    if posts:
        counts: dict[str, int] = defaultdict(int)
        for post in posts[:80]:
            for term in extract_query_terms(post.text):
                if len(term) >= 4:
                    counts[term] += 1

        ranked_terms = sorted(
            counts.items(),
            key=lambda item: (-item[1], -len(item[0]), item[0]),
        )
        for term, _ in ranked_terms[:12]:
            add_term(term)

    return terms[:NEWS_TERM_LIMIT]


def build_social_keyword_query(query: str, posts: list[SourcedPost] | None = None) -> str:
    keywords: list[str] = []
    seen: set[str] = set()

    def add_keyword(value: str) -> None:
        clean = value.strip().lower()
        if not clean or clean in seen:
            return
        seen.add(clean)
        keywords.append(clean)

    for term in extract_query_terms(query):
        if " " not in term:
            add_keyword(term)

    if posts:
        for post in posts[:25]:
            for term in extract_query_terms(post.text):
                if " " not in term:
                    add_keyword(term)

    if not keywords:
        return query
    return ",".join(keywords[:6])


def choose_category(market: dict[str, Any]) -> str | None:
    for key in ("category", "groupItemTitle", "eventType", "series"):
        value = market.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    tags = market.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                label = tag.get("label") or tag.get("name")
                if isinstance(label, str) and label.strip():
                    return label.strip()
            elif isinstance(tag, str) and tag.strip():
                return tag.strip()

    return None


def tag_labels(value: Any) -> list[str]:
    labels: list[str] = []
    if not isinstance(value, list):
        return labels

    for item in value:
        if isinstance(item, dict):
            label = item.get("label") or item.get("name") or item.get("slug")
            if isinstance(label, str) and label.strip():
                labels.append(label.strip())
        elif isinstance(item, str) and item.strip():
            labels.append(item.strip())

    return labels


def market_context_text(market: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for key in (
        "subtitle",
        "description",
        "groupItemTitle",
        "series",
        "event_title",
        "event_subtitle",
        "event_description",
        "series_ticker",
        "event_ticker",
        "yes_sub_title",
        "no_sub_title",
    ):
        value = market.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    parts.extend(tag_labels(market.get("tags")))
    if not parts:
        return None
    return " ".join(parts)


def market_url(market: dict[str, Any]) -> str | None:
    direct_url = market.get("url")
    if isinstance(direct_url, str) and direct_url.strip():
        return direct_url

    slug = market.get("slug") or market.get("marketSlug")
    if isinstance(slug, str) and slug.strip():
        return f"https://polymarket.com/event/{slug.strip()}"
    return None


def market_question(market: dict[str, Any]) -> str:
    for key in ("question", "title"):
        value = market.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Untitled market"


def extract_yes_no_probabilities(market: dict[str, Any]) -> tuple[float | None, float | None]:
    outcome_labels = [label.lower() for label in coerce_text_list(market.get("outcomes"))]
    outcome_prices = coerce_number_list(market.get("outcomePrices"))

    if outcome_labels and outcome_prices and len(outcome_labels) == len(outcome_prices):
        lookup = dict(zip(outcome_labels, outcome_prices))
        yes_probability = clamp_probability(lookup.get("yes"))
        no_probability = clamp_probability(lookup.get("no"))
        if yes_probability is not None or no_probability is not None:
            return yes_probability, no_probability

    yes_probability = clamp_probability(
        market.get("yes_probability")
        or market.get("probability")
        or market.get("lastTradePrice")
        or market.get("bestAsk")
    )

    no_probability = clamp_probability(market.get("no_probability"))
    if yes_probability is not None and no_probability is None:
        no_probability = round(1 - yes_probability, 4)
    elif no_probability is not None and yes_probability is None:
        yes_probability = round(1 - no_probability, 4)

    return yes_probability, no_probability


def normalize_polymarket_prediction(item: dict[str, Any]) -> Prediction | None:
    question = market_question(item)
    source = str(item.get("source") or "polymarket").strip().lower()

    if source != "polymarket":
        return None

    yes_probability, no_probability = extract_yes_no_probabilities(item)
    closes_at = item.get("closes_at") or item.get("endDate") or item.get("closeDate")

    return Prediction(
        id=str(item.get("id") or item.get("conditionId") or question),
        source=source,
        question=question,
        category=choose_category(item) or item.get("event_title") or item.get("subtitle"),
        context=market_context_text(item),
        yes_probability=yes_probability,
        no_probability=no_probability,
        volume_usd=item.get("volume_usd") or item.get("volume") or item.get("volumeNum"),
        liquidity_usd=(
            item.get("liquidity_usd") or item.get("liquidity") or item.get("liquidityNum")
        ),
        closes_at=str(closes_at) if closes_at else None,
        url=market_url(item),
    )


def normalize_kalshi_prediction(item: dict[str, Any]) -> Prediction | None:
    question = str(
        item.get("title")
        or item.get("yes_sub_title")
        or item.get("subtitle")
        or item.get("question")
        or ""
    ).strip()
    if not question:
        return None

    yes_probability = clamp_probability(
        item.get("yes_ask_dollars")
        or item.get("yes_bid_dollars")
        or item.get("last_price_dollars")
        or item.get("yes_ask")
        or item.get("yes_bid")
        or item.get("last_price")
        or item.get("yes_price")
    )
    no_probability = clamp_probability(
        item.get("no_ask_dollars")
        or item.get("no_bid_dollars")
        or item.get("no_ask")
        or item.get("no_bid")
        or item.get("no_price")
    )
    if yes_probability is not None and no_probability is None:
        no_probability = round(1 - yes_probability, 4)
    elif no_probability is not None and yes_probability is None:
        yes_probability = round(1 - no_probability, 4)

    closes_at = item.get("close_time") or item.get("expiration_time") or item.get("close_date")
    category = item.get("series_ticker") or item.get("event_ticker") or item.get("status")
    ticker = str(item.get("ticker") or item.get("market_ticker") or question)
    return Prediction(
        id=ticker,
        source="kalshi",
        question=question,
        category=str(category).strip().lower() if category else "general",
        context=market_context_text(item),
        yes_probability=yes_probability,
        no_probability=no_probability,
        volume_usd=(
            normalize_number(item.get("volume_dollars"))
            or normalize_number(item.get("volume_fp"))
            or normalize_number(item.get("volume_24h_fp"))
            or normalize_number(item.get("volume"))
        ),
        liquidity_usd=(
            normalize_number(item.get("liquidity_dollars"))
            or normalize_number(item.get("open_interest_fp"))
            or normalize_number(item.get("liquidity"))
        ),
        closes_at=normalize_timestamp(closes_at) if closes_at else None,
        url=f"https://kalshi.com/markets/{ticker.lower()}",
    )


def prediction_dedupe_key(prediction: Prediction) -> str:
    return f"{prediction.source}:{prediction.id}"


def post_dedupe_key(post: SourcedPost) -> str:
    return post.id or f"{post.source}:{post.url or post.text}"


def prediction_haystack(prediction: Prediction) -> str:
    haystack_parts = [prediction.question]
    if prediction.category:
        haystack_parts.append(prediction.category)
    if prediction.context:
        haystack_parts.append(prediction.context)
    if prediction.url:
        haystack_parts.append(prediction.url)
    return " ".join(haystack_parts).lower()


def prediction_popularity_score(prediction: Prediction) -> float:
    volume = max(float(prediction.volume_usd or 0.0), 0.0)
    liquidity = max(float(prediction.liquidity_usd or 0.0), 0.0)

    volume_score = min(math.log10(volume + 1.0) / 6.0, 1.0)
    liquidity_score = min(math.log10(liquidity + 1.0) / 5.6, 1.0)

    if volume <= 0 and liquidity <= 0:
        return 0.0

    return round(volume_score * 0.65 + liquidity_score * 0.35, 4)


def query_anchor_terms(query: str) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()
    for term in extract_query_terms(query):
        if len(term) < 3:
            continue
        term_tokens = tokenize(term)
        if len(term_tokens) == 1 and next(iter(term_tokens), "") in WEAK_QUERY_TOKENS:
            continue
        if term in seen:
            continue
        seen.add(term)
        anchors.append(term)
    return anchors[:10]


def score_prediction(query: str, search_terms: list[str], prediction: Prediction) -> float:
    if not search_terms:
        return 0.0

    haystack = prediction_haystack(prediction)
    haystack_tokens = tokenize(haystack)
    anchor_terms = query_anchor_terms(query)
    if anchor_terms:
        anchor_matches = 0
        multiword_anchor_matches = 0
        for term in anchor_terms:
            term_tokens = tokenize(term)
            if not term_tokens:
                continue
            if term in haystack or term_tokens.issubset(haystack_tokens):
                anchor_matches += 1
                if len(term_tokens) >= 2:
                    multiword_anchor_matches += 1

        if anchor_matches == 0:
            return 0.0
    else:
        anchor_matches = 0
        multiword_anchor_matches = 0

    score = 0.0
    matched = False
    primary_query_tokens = {
        token
        for token in tokenize(query)
        if token not in QUERY_STOP_WORDS and token not in WEAK_QUERY_TOKENS and len(token) >= 3
    }
    strong_query_tokens = {token for token in primary_query_tokens if len(token) >= 4}
    primary_overlap = primary_query_tokens & haystack_tokens
    overlap_ratio = len(primary_overlap) / max(len(primary_query_tokens), 1)
    semantic_similarity = 0.0
    if primary_overlap:
        score += float(len(primary_overlap) * 18)
        score += (len(primary_overlap) / max(len(primary_query_tokens), 1)) * 16
    score += float(anchor_matches * 20)

    for term in search_terms:
        query_text = term.strip().lower()
        query_tokens = tokenize(query_text)
        if not query_tokens:
            continue

        overlap = len(query_tokens & haystack_tokens)
        if overlap == 0 and query_text not in haystack:
            continue

        matched = True
        score += float(overlap * 7)
        if query_text in haystack:
            score += 12
        score += (overlap / max(len(query_tokens), 1)) * 6

    if matched or primary_overlap or anchor_matches > 0:
        semantic_similarity = semantic_text_similarity(query, haystack)
        score += semantic_similarity * 42

    if (
        len(strong_query_tokens) >= 2
        and len(primary_overlap) < 2
        and multiword_anchor_matches == 0
        and semantic_similarity < 0.62
    ):
        return 0.0

    if (
        anchor_terms
        and anchor_matches == 0
        and overlap_ratio < 0.18
        and semantic_similarity < max(PREDICTION_MIN_EMBEDDING_SIM, 0.56)
    ):
        return 0.0

    if not matched and not primary_overlap and semantic_similarity < PREDICTION_MIN_EMBEDDING_SIM:
        return 0.0

    popularity = prediction_popularity_score(prediction)
    score += popularity * 18

    if (
        popularity < PREDICTION_MIN_POPULARITY_FLOOR
        and semantic_similarity < 0.74
        and overlap_ratio < 0.58
        and anchor_matches < 2
    ):
        return 0.0

    if score < PREDICTION_MIN_SCORE and semantic_similarity < max(PREDICTION_MIN_EMBEDDING_SIM, 0.46):
        return 0.0

    prediction.relevance_score = round(
        min(
            1.0,
            semantic_similarity * 0.58
            + overlap_ratio * 0.2
            + min(anchor_matches, 3) * 0.08
            + min(len(primary_overlap), 3) * 0.05,
        ),
        4,
    )
    return score


def parse_sample_predictions() -> list[Prediction]:
    raw = SAMPLE_DATA_PATH.read_text(encoding="utf-8").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or start >= end:
        raise ValueError(f"Could not parse JSON in {SAMPLE_DATA_PATH}")

    payload = json.loads(raw[start : end + 1])
    predictions = []
    for item in payload.get("predictions", []):
        prediction = normalize_polymarket_prediction(item)
        if prediction is not None:
            predictions.append(prediction)
    return predictions


async def fetch_live_polymarket_predictions(
    client: httpx.AsyncClient,
    *,
    include_closed: bool,
) -> list[Prediction]:
    predictions: list[Prediction] = []

    for page in range(POLYMARKET_MAX_PAGES):
        params = {
            "limit": POLYMARKET_PAGE_SIZE,
            "offset": page * POLYMARKET_PAGE_SIZE,
            "archived": "false",
        }
        if not include_closed:
            params["active"] = "true"
            params["closed"] = "false"

        response = await client.get(GAMMA_MARKETS_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Unexpected Polymarket markets response format")

        for item in payload:
            if not isinstance(item, dict):
                continue
            item["source"] = "polymarket"
            prediction = normalize_polymarket_prediction(item)
            if prediction is not None:
                predictions.append(prediction)

        if len(payload) < POLYMARKET_PAGE_SIZE:
            break

    event_params = {
        "limit": 250,
        "offset": 0,
        "archived": "false",
    }
    if not include_closed:
        event_params["active"] = "true"
        event_params["closed"] = "false"

    try:
        response = await client.get(GAMMA_EVENTS_URL, params=event_params)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            for event in payload:
                if not isinstance(event, dict):
                    continue
                for market in event.get("markets", []):
                    if not isinstance(market, dict):
                        continue
                    market.setdefault("source", "polymarket")
                    market.setdefault("category", event.get("category") or event.get("title"))
                    prediction = normalize_polymarket_prediction(market)
                    if prediction is not None:
                        predictions.append(prediction)
    except Exception:
        pass

    return predictions


async def fetch_polymarket_search_predictions(
    client: httpx.AsyncClient,
    *,
    query: str,
    search_terms: list[str] | None,
    include_closed: bool,
) -> list[Prediction]:
    predictions: list[Prediction] = []
    seen_terms: set[str] = set()
    multiword_terms: list[str] = []
    single_terms: list[str] = []

    for value in [query, *(search_terms or [])]:
        clean = re.sub(r"\s+", " ", str(value or "")).strip()
        if not clean:
            continue
        lowered = clean.lower()
        if lowered in seen_terms:
            continue
        seen_terms.add(lowered)
        if " " in clean:
            multiword_terms.append(clean)
        else:
            single_terms.append(clean)

    terms = multiword_terms[:POLYMARKET_PUBLIC_SEARCH_TERMS]
    if len(terms) < 2:
        terms.extend(single_terms[: POLYMARKET_PUBLIC_SEARCH_TERMS - len(terms)])
    elif len(terms) < POLYMARKET_PUBLIC_SEARCH_TERMS:
        terms.extend(single_terms[:1])

    for term in terms:
        payload: dict[str, Any] | None = None
        for params in (
            {"q": term, "limit": POLYMARKET_PUBLIC_SEARCH_LIMIT},
            {"query": term, "limit": POLYMARKET_PUBLIC_SEARCH_LIMIT},
        ):
            try:
                response = await client.get(GAMMA_PUBLIC_SEARCH_URL, params=params)
                response.raise_for_status()
                candidate = response.json()
            except Exception:
                continue

            if isinstance(candidate, dict):
                payload = candidate
                break

        if payload is None:
            continue

        for market in payload.get("markets", []):
            if not isinstance(market, dict):
                continue
            market.setdefault("source", "polymarket")
            prediction = normalize_polymarket_prediction(market)
            if prediction is not None:
                predictions.append(prediction)

        for event in payload.get("events", []):
            if not isinstance(event, dict):
                continue

            event_active = bool(event.get("active", True))
            event_closed = bool(event.get("closed", False))
            event_slug = str(event.get("slug") or "").strip()
            event_url = f"https://polymarket.com/event/{event_slug}" if event_slug else None
            event_title = str(event.get("title") or "").strip()
            event_subtitle = str(event.get("subtitle") or "").strip()
            event_description = str(event.get("description") or "").strip()
            event_category = event.get("category") or event.get("subcategory")

            for market in event.get("markets", []):
                if not isinstance(market, dict):
                    continue
                market_active = bool(market.get("active", event_active))
                market_closed = bool(market.get("closed", event_closed))
                if not include_closed and (not market_active or market_closed):
                    continue

                enriched_market = dict(market)
                enriched_market.setdefault("source", "polymarket")
                enriched_market.setdefault("url", event_url)
                enriched_market.setdefault("category", event_category or event_title)
                enriched_market.setdefault("event_title", event_title)
                enriched_market.setdefault("event_subtitle", event_subtitle)
                enriched_market.setdefault("event_description", event_description)
                prediction = normalize_polymarket_prediction(enriched_market)
                if prediction is not None:
                    predictions.append(prediction)

    return predictions


async def fetch_live_kalshi_predictions(
    client: httpx.AsyncClient,
    *,
    include_closed: bool,
) -> list[Prediction]:
    predictions: list[Prediction] = []
    cursor: str | None = None

    for _ in range(KALSHI_MAX_PAGES):
        params: dict[str, Any] = {"limit": KALSHI_PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        if not include_closed:
            params["status"] = "open"

        response = await client.get(KALSHI_MARKETS_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Kalshi response format")

        markets = payload.get("markets", [])
        if not isinstance(markets, list):
            break

        for item in markets:
            if not isinstance(item, dict):
                continue
            prediction = normalize_kalshi_prediction(item)
            if prediction is not None:
                predictions.append(prediction)

        cursor = payload.get("cursor") or None
        if not cursor:
            break

    return predictions


def merge_predictions(prediction_lists: list[list[Prediction]]) -> list[Prediction]:
    merged: list[Prediction] = []
    seen: set[str] = set()
    for prediction_list in prediction_lists:
        for prediction in prediction_list:
            key = prediction_dedupe_key(prediction)
            if key in seen:
                continue
            seen.add(key)
            merged.append(prediction)
    return merged


def merge_posts(post_lists: list[list[SourcedPost]]) -> list[SourcedPost]:
    merged: list[SourcedPost] = []
    seen: set[str] = set()
    for post_list in post_lists:
        for post in post_list:
            key = post_dedupe_key(post)
            if key in seen:
                continue
            seen.add(key)
            merged.append(post)

    merged.sort(key=lambda post: parse_datetime(post.timestamp), reverse=True)
    return merged


def rank_predictions(
    query: str,
    predictions: list[Prediction],
    search_terms: list[str] | None = None,
) -> list[Prediction]:
    effective_terms = search_terms or build_market_search_terms(query)
    scored: list[tuple[float, float, Prediction]] = []
    seen_ids: set[str] = set()

    for prediction in predictions:
        dedupe_key = prediction_dedupe_key(prediction)
        if dedupe_key in seen_ids:
            continue
        seen_ids.add(dedupe_key)

        score = score_prediction(query, effective_terms, prediction)
        if score > 0:
            popularity = prediction_popularity_score(prediction)
            scored.append((score, popularity, prediction))

    scored.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2].volume_usd or 0,
            item[2].liquidity_usd or 0,
        ),
        reverse=True,
    )
    return [prediction for _, _, prediction in scored]


async def search_predictions(
    request: SearchRequest,
    search_terms: list[str] | None = None,
) -> tuple[list[Prediction], str]:
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            public_search_predictions = await fetch_polymarket_search_predictions(
                client,
                query=request.query,
                search_terms=search_terms,
                include_closed=request.include_closed,
            )
            fast_predictions = rank_predictions(
                request.query,
                public_search_predictions,
                search_terms=search_terms,
            )
            fast_path_threshold = min(request.limit, 6)
            if len(fast_predictions) >= fast_path_threshold or (
                request.limit <= 10 and len(fast_predictions) >= 4
            ):
                return fast_predictions[: request.limit], "live"

            polymarket_predictions, kalshi_predictions = await asyncio.gather(
                fetch_live_polymarket_predictions(
                    client,
                    include_closed=request.include_closed,
                ),
                fetch_live_kalshi_predictions(
                    client,
                    include_closed=request.include_closed,
                ),
                return_exceptions=True,
            )

        live_predictions = merge_predictions(
            [
                public_search_predictions,
                polymarket_predictions if not isinstance(polymarket_predictions, Exception) else [],
                kalshi_predictions if not isinstance(kalshi_predictions, Exception) else [],
            ]
        )
        live_predictions = rank_predictions(
            request.query,
            live_predictions,
            search_terms=search_terms,
        )
        if live_predictions:
            return live_predictions[: request.limit], "live"
        return [], "live"
    except Exception:
        pass

    fallback_predictions = rank_predictions(
        request.query,
        parse_sample_predictions(),
        search_terms=search_terms,
    )
    return fallback_predictions[: request.limit], "sample"


async def build_search_suggestions(query: str, limit: int = 8) -> dict[str, Any]:
    warnings: list[str] = []
    news_terms = build_news_search_terms(query)[:2]
    posts: list[SourcedPost] = []

    if data_google_news is None:
        if GOOGLE_NEWS_IMPORT_ERROR:
            warnings.append(f"google_news unavailable: {GOOGLE_NEWS_IMPORT_ERROR}")
    else:
        news_results = await asyncio.gather(
            *(data_google_news.fetch(term, max_results=12) for term in news_terms),
            return_exceptions=True,
        )
        for term, result in zip(news_terms, news_results):
            if isinstance(result, Exception):
                warnings.append(f"google_news:{term} fetch failed: {result}")
                continue
            for item in result:
                post = normalize_source_post(item)
                if post is not None:
                    posts.append(post)
        posts = merge_posts([posts])

    try:
        hn_posts = await fetch_hackernews_posts(query, max_results=8)
    except Exception as exc:
        warnings.append(f"hackernews fetch failed: {exc}")
    else:
        posts = merge_posts([posts, hn_posts])

    posts = merge_posts([posts, load_cached_posts(query, limit=40)])

    market_terms = build_market_search_terms(query, posts)
    predictions, prediction_source = await search_predictions(
        SearchRequest(query=query, limit=max(limit, 6)),
        search_terms=market_terms,
    )
    events = synthesize_events(posts, [], max(limit, 6), query=query)

    suggestions: list[str] = []
    seen: set[str] = set()

    def add_suggestion(value: str) -> None:
        clean = re.sub(r"\s+", " ", value).strip()
        if not clean:
            return
        key = clean.lower()
        if key in seen:
            return
        seen.add(key)
        suggestions.append(clean)

    add_suggestion(query)
    for event in events:
        add_suggestion(event.title)
    for prediction in predictions:
        add_suggestion(prediction.question)
    for term in news_terms:
        if " " in term:
            add_suggestion(term.title())

    return {
        "query": query,
        "fetched_at": utc_now_iso(),
        "source_mode": prediction_source,
        "warnings": warnings,
        "suggestions": suggestions[:limit],
    }


def serialize_prediction(prediction: Prediction) -> dict[str, Any]:
    return prediction.model_dump(exclude_none=True)


def ndjson_line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def serialize_post(post: SourcedPost) -> dict[str, Any]:
    return post.model_dump(exclude_none=True)


def serialize_event(event: WorkflowEvent) -> dict[str, Any]:
    return event.model_dump(exclude_none=True)


async def fetch_hackernews_posts(query: str, max_results: int = HACKERNEWS_RESULTS_PER_TERM) -> list[SourcedPost]:
    terms = build_news_search_terms(query)[:HACKERNEWS_TERM_LIMIT]
    posts: list[SourcedPost] = []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for term in terms:
            response = await client.get(
                HACKERNEWS_SEARCH_URL,
                params={
                    "query": term,
                    "tags": "story",
                    "hitsPerPage": max_results,
                },
            )
            response.raise_for_status()
            payload = response.json()
            hits = payload.get("hits", [])
            if not isinstance(hits, list):
                continue

            for hit in hits:
                if not isinstance(hit, dict):
                    continue
                title = str(hit.get("title") or hit.get("story_title") or "").strip()
                if not title:
                    continue
                url = str(hit.get("url") or hit.get("story_url") or "").strip() or None
                post = normalize_source_post(
                    {
                        "id": f"hn_{hit.get('objectID') or abs(hash(title))}",
                        "source": "hackernews",
                        "author": str(hit.get("author") or "hackernews"),
                        "text": title,
                        "timestamp": hit.get("created_at"),
                        "url": url or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    }
                )
                if post is not None:
                    posts.append(post)

    return merge_posts([posts])


async def fetch_rss_posts(query: str, max_results: int = RSS_RESULTS_PER_FEED) -> list[SourcedPost]:
    posts: list[SourcedPost] = []
    feed_items = list(RSS_FEEDS.items())[:RSS_FEED_LIMIT]

    async def fetch_feed(name: str, url: str) -> list[SourcedPost]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            root = ET.fromstring(response.text)

        feed_posts: list[SourcedPost] = []
        for item in root.findall(".//item"):
            title = plain_text(item.findtext("title", ""))
            description = plain_text(item.findtext("description", ""))
            combined_text = f"{title}. {description}".strip(". ").strip()
            if not combined_text:
                continue

            post = normalize_source_post(
                {
                    "id": f"rss_{hashlib.md5((item.findtext('link', '') or title).encode('utf-8')).hexdigest()[:12]}",
                    "source": "rss",
                    "author": name,
                    "text": shorten(combined_text, 320),
                    "timestamp": item.findtext("pubDate", ""),
                    "url": item.findtext("link", ""),
                }
            )
            if post is None or score_post_query_relevance(query, post) <= 0:
                continue
            feed_posts.append(post)

        return merge_posts([feed_posts])[:max_results]

    results = await asyncio.gather(
        *(fetch_feed(name, url) for name, url in feed_items),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, Exception):
            continue
        posts.extend(result)
    return merge_posts([posts])


async def fetch_reddit_posts(query: str, max_results: int = REDDIT_RESULTS_PER_QUERY) -> list[SourcedPost]:
    posts: list[SourcedPost] = []
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=REDDIT_HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as client:
        google_response = await client.get(
            GOOGLE_NEWS_RSS_URL,
            params={
                "q": f"{query} site:reddit.com",
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            },
        )
        google_response.raise_for_status()
        google_root = ET.fromstring(google_response.text)
        for item in google_root.findall(".//item"):
            post = normalize_source_post(
                {
                    "id": f"reddit_g_{hashlib.md5((item.findtext('link', '') or item.findtext('title', '')).encode('utf-8')).hexdigest()[:12]}",
                    "source": "reddit",
                    "author": "Reddit",
                    "text": plain_text(item.findtext("title", "")),
                    "timestamp": item.findtext("pubDate", ""),
                    "url": item.findtext("link", ""),
                }
            )
            if post is not None:
                posts.append(post)

        reddit_response = await client.get(
            "https://www.reddit.com/search.json",
            params={
                "q": query,
                "sort": "new",
                "limit": min(max_results, 25),
                "t": "month",
            },
        )
        if reddit_response.status_code == 200:
            payload = reddit_response.json()
            for item in payload.get("data", {}).get("children", []):
                data = item.get("data", {})
                text = plain_text(
                    f"{data.get('title', '')}. {str(data.get('selftext', '') or '')[:260]}"
                )
                post = normalize_source_post(
                    {
                        "id": f"reddit_{data.get('id', '')}",
                        "source": "reddit",
                        "author": f"r/{data.get('subreddit', '?')} u/{data.get('author', '?')}",
                        "text": text,
                        "timestamp": data.get("created_utc"),
                        "url": f"https://reddit.com{data.get('permalink', '')}",
                    }
                )
                if post is None or score_post_query_relevance(query, post) <= 0:
                    continue
                posts.append(post)

    return merge_posts([posts])[:max_results]


def format_compact_number(value: float | None) -> str:
    if value is None:
        return "0"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}k"
    return f"{value:.0f}"


def shorten(text: str, max_length: int = 78) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_length:
        return clean
    return clean[: max_length - 1].rstrip() + "…"


def guess_event_title(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return "Untitled event"
    sentence = re.split(r"(?<=[.!?])\s+", clean, maxsplit=1)[0]
    return shorten(sentence, 72)


def normalize_source_post(item: Any) -> SourcedPost | None:
    def read_attr(name: str, default: Any = "") -> Any:
        if isinstance(item, dict):
            return item.get(name, default)
        return getattr(item, name, default)

    text = str(read_attr("text", "") or "").strip()
    if not text:
        return None

    source = str(read_attr("source", "") or "unknown").strip() or "unknown"
    author = str(read_attr("author", "") or source).strip() or source
    return SourcedPost(
        id=str(read_attr("id", "") or f"{source}-{abs(hash(text))}"),
        source=source,
        author=author,
        text=text,
        timestamp=normalize_timestamp(read_attr("timestamp", None)),
        url=read_attr("url", None),
        recency_tag=str(read_attr("recency_tag", "") or classify_recency_tag(read_attr("timestamp", None))),
    )


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def important_text_tokens(text: str, *, min_length: int = 4, limit: int = 10) -> list[str]:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in QUERY_STOP_WORDS and token not in WEAK_QUERY_TOKENS and len(token) >= min_length
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped[:limit]


def score_post_query_relevance(query: str, post: SourcedPost) -> float:
    haystack = f"{post.text} {post.author} {post.source}".lower()
    haystack_tokens = tokenize(haystack)
    query_tokens = set(important_text_tokens(query, min_length=3, limit=12))
    overlap = len(query_tokens & haystack_tokens)
    score = float(overlap * 10)

    normalized_query = normalize_key(query)
    if normalized_query and normalized_query in normalize_key(post.text):
        score += 22

    for term in query_anchor_terms(query):
        term_tokens = tokenize(term)
        if not term_tokens:
            continue
        if term in haystack or term_tokens.issubset(haystack_tokens):
            score += 12 if len(term_tokens) >= 2 else 4

    return score


def plain_text(value: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def cache_post_key(post: SourcedPost) -> str:
    return hashlib.sha256(
        "||".join(
            [
                post.id,
                post.source,
                post.author,
                normalize_timestamp(post.timestamp),
                post.url or "",
                post.text,
            ]
        ).encode("utf-8")
    ).hexdigest()


def store_posts_in_cache(query: str, posts: list[SourcedPost]) -> None:
    if not posts:
        return

    init_source_cache()
    collected_at = utc_now_iso()
    with get_cache_connection() as connection:
        connection.executemany(
            """
            INSERT OR REPLACE INTO cached_posts (
                cache_key,
                post_id,
                source,
                author,
                text,
                timestamp,
                url,
                recency_tag,
                query,
                collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    cache_post_key(post),
                    post.id,
                    post.source,
                    post.author,
                    post.text,
                    normalize_timestamp(post.timestamp),
                    post.url,
                    post.recency_tag or classify_recency_tag(post.timestamp),
                    query,
                    collected_at,
                )
                for post in posts
            ],
        )


def load_cached_posts(query: str, limit: int = CACHED_POST_LIMIT) -> list[SourcedPost]:
    init_source_cache()
    query_terms = important_text_tokens(query, min_length=3, limit=6)
    if not query_terms:
        return []

    lookback_cutoff = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .astimezone(timezone.utc)
    )
    lookback_cutoff = lookback_cutoff.timestamp() - (CACHED_POST_LOOKBACK_DAYS * 86400)
    cutoff_iso = datetime.fromtimestamp(lookback_cutoff, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    query_clauses: list[str] = []
    params: list[Any] = [cutoff_iso]
    for term in query_terms:
        like_value = f"%{term}%"
        query_clauses.append("(lower(text) LIKE ? OR lower(author) LIKE ? OR lower(source) LIKE ?)")
        params.extend([like_value, like_value, like_value])

    sql = f"""
        SELECT post_id, source, author, text, timestamp, url, recency_tag
        FROM cached_posts
        WHERE timestamp >= ?
          AND ({' OR '.join(query_clauses)})
        ORDER BY timestamp DESC
        LIMIT 600
    """
    with get_cache_connection() as connection:
        rows = connection.execute(sql, params).fetchall()

    scored_posts: list[tuple[float, SourcedPost]] = []
    for row in rows:
        post = normalize_source_post(
            {
                "id": row["post_id"],
                "source": row["source"],
                "author": row["author"],
                "text": row["text"],
                "timestamp": row["timestamp"],
                "url": row["url"],
                "recency_tag": row["recency_tag"],
            }
        )
        if post is None:
            continue
        score = score_post_query_relevance(query, post)
        if score <= 0:
            continue
        scored_posts.append((score, post))

    scored_posts.sort(
        key=lambda current: (
            current[0],
            parse_datetime(current[1].timestamp).timestamp(),
        ),
        reverse=True,
    )
    return merge_posts([[post for _, post in scored_posts[:limit]]])


def select_analysis_posts(
    query: str,
    posts: list[SourcedPost],
    limit: int = MAX_ANALYSIS_POSTS,
) -> list[SourcedPost]:
    if len(posts) <= limit:
        return posts

    ranked_posts = sorted(
        posts,
        key=lambda post: (
            score_post_query_relevance(query, post),
            parse_datetime(post.timestamp).timestamp(),
        ),
        reverse=True,
    )
    selected = ranked_posts[:limit]
    selected.sort(key=lambda post: parse_datetime(post.timestamp), reverse=True)
    return selected


def source_item_signature(
    *,
    text: str,
    source: str,
    timestamp: str,
    url: str | None,
) -> str:
    return "||".join(
        [
            normalize_key(text),
            normalize_key(source),
            normalize_timestamp(timestamp),
            normalize_key(url or ""),
        ]
    )


def choose_event_stack_key(
    entities: list[str],
    topic_tags: list[str],
    text: str,
) -> str:
    for entity in entities:
        normalized = normalize_key(entity)
        if len(normalized) >= 4:
            return normalized

    for topic in topic_tags:
        normalized = normalize_key(topic)
        if len(normalized) >= 4:
            return normalized

    tokens = important_text_tokens(text, limit=3)
    return tokens[0] if tokens else "general"


def event_haystack(event: WorkflowEvent) -> str:
    parts = [
        event.title,
        event.description,
        " ".join(event.entities),
        " ".join(event.topic_tags),
    ]
    for source in event.sources[:5]:
        text = str(source.get("text") or source.get("summary") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def score_event_query_relevance(query: str, event: WorkflowEvent) -> float:
    haystack = event_haystack(event)
    haystack_lower = haystack.lower()
    haystack_tokens = tokenize(haystack_lower)
    query_tokens = set(important_text_tokens(query, min_length=3, limit=12))
    overlap = len(query_tokens & haystack_tokens)
    overlap_ratio = overlap / max(len(query_tokens), 1)
    anchor_hits = 0
    for term in query_anchor_terms(query):
        term_tokens = tokenize(term)
        if not term_tokens:
            continue
        if term in haystack_lower or term_tokens.issubset(haystack_tokens):
            anchor_hits += 1

    semantic_similarity = semantic_text_similarity(query, haystack)
    base_relevance = float(event.relevance_score or 0.0)
    source_bonus = min(event.source_count, 4) * 0.03

    score = min(
        1.0,
        base_relevance * 0.34
        + semantic_similarity * 0.42
        + overlap_ratio * 0.14
        + min(anchor_hits, 3) * 0.08
        + source_bonus,
    )
    return round(score, 4)


def build_event_candidate_items(
    posts: list[SourcedPost],
    enriched_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if enriched_items:
        post_by_signature = {
            source_item_signature(
                text=post.text,
                source=post.source,
                timestamp=post.timestamp,
                url=post.url,
            ): post
            for post in posts
        }

        items: list[dict[str, Any]] = []
        for item in enriched_items:
            signature = source_item_signature(
                text=str(item.get("text") or ""),
                source=str(item.get("source") or ""),
                timestamp=str(item.get("timestamp") or utc_now_iso()),
                url=item.get("url"),
            )
            matched_post = post_by_signature.get(signature)
            items.append(
                {
                    "id": matched_post.id if matched_post else signature,
                    "text": str(item.get("text") or ""),
                    "source": str(item.get("source") or "unknown"),
                    "author": matched_post.author if matched_post else str(item.get("source") or "unknown"),
                    "timestamp": normalize_timestamp(item.get("timestamp")),
                    "url": matched_post.url if matched_post else item.get("url"),
                    "sentiment_score": item.get("sentiment_score"),
                    "relevance_score": float(item.get("relevance_score") or 0.0),
                    "topic_tags": [
                        *[str(tag) for tag in item.get("topic_tags", [])],
                        *(
                            [matched_post.recency_tag]
                            if matched_post and matched_post.recency_tag in {"context", "historical"}
                            else []
                        ),
                    ],
                    "entities": [str(entity) for entity in item.get("entities", [])],
                }
            )
        return items

    return [
        {
            "id": post.id,
            "text": post.text,
            "source": post.source,
            "author": post.author,
            "timestamp": post.timestamp,
            "url": post.url,
            "sentiment_score": None,
            "relevance_score": 0.0,
            "topic_tags": [post.recency_tag] if post.recency_tag in {"context", "historical"} else [],
            "entities": [],
        }
        for post in posts
    ]


def synthesize_events(
    posts: list[SourcedPost],
    enriched_items: list[dict[str, Any]],
    max_events: int,
    *,
    query: str | None = None,
) -> list[WorkflowEvent]:
    items = build_event_candidate_items(posts, enriched_items)
    if not items:
        return []

    clusters: list[dict[str, Any]] = []
    sorted_items = sorted(items, key=lambda item: parse_datetime(item["timestamp"]))

    for item in sorted_items:
        item_time = parse_datetime(item["timestamp"])
        item_entities = {
            normalize_key(entity)
            for entity in item.get("entities", [])
            if len(normalize_key(entity)) >= 4
        }
        item_topics = {
            normalize_key(topic)
            for topic in item.get("topic_tags", [])
            if len(normalize_key(topic)) >= 4
        }
        item_tokens = set(important_text_tokens(item["text"], limit=8))

        best_cluster: dict[str, Any] | None = None
        best_score = 0.0

        for cluster in clusters[-24:]:
            time_diff_hours = abs(
                (item_time - cluster["latest_time"]).total_seconds()
            ) / 3600
            if time_diff_hours > EVENT_CLUSTER_WINDOW_HOURS:
                continue

            entity_overlap = len(item_entities & cluster["entity_keys"])
            topic_overlap = len(item_topics & cluster["topic_keys"])
            token_overlap = len(item_tokens & cluster["token_keys"])
            score = float(entity_overlap * 6 + topic_overlap * 3 + token_overlap * 2)
            if item["source"] not in cluster["source_labels"]:
                score += 1.0

            if score > best_score:
                best_score = score
                best_cluster = cluster

        if best_cluster is None or best_score < EVENT_CLUSTER_MIN_MERGE_SCORE:
            clusters.append(
                {
                    "items": [item],
                    "earliest_time": item_time,
                    "latest_time": item_time,
                    "entity_keys": set(item_entities),
                    "topic_keys": set(item_topics),
                    "token_keys": set(item_tokens),
                    "source_labels": {item["source"]},
                }
            )
            continue

        best_cluster["items"].append(item)
        best_cluster["earliest_time"] = min(best_cluster["earliest_time"], item_time)
        best_cluster["latest_time"] = max(best_cluster["latest_time"], item_time)
        best_cluster["entity_keys"].update(item_entities)
        best_cluster["topic_keys"].update(item_topics)
        best_cluster["token_keys"].update(item_tokens)
        best_cluster["source_labels"].add(item["source"])

    ranked_clusters = sorted(
        clusters,
        key=lambda cluster: (
            sum(float(item.get("relevance_score") or 0.0) for item in cluster["items"])
            / max(len(cluster["items"]), 1),
            len(cluster["source_labels"]) >= 2 or len(cluster["items"]) >= 2,
            len(cluster["source_labels"]),
            len(cluster["items"]),
            cluster["latest_time"].timestamp(),
        ),
        reverse=True,
    )

    preferred_clusters = []
    for cluster in ranked_clusters:
        cluster_relevance = (
            sum(float(item.get("relevance_score") or 0.0) for item in cluster["items"])
            / max(len(cluster["items"]), 1)
        )
        if (
            len(cluster["source_labels"]) >= 2
            or len(cluster["items"]) >= 2
            or cluster_relevance >= 0.62
        ):
            preferred_clusters.append(cluster)

    if len(preferred_clusters) < min(max_events, 4):
        preferred_clusters = ranked_clusters

    candidate_limit = max(max_events * 6, 18)
    selected_clusters = preferred_clusters[:candidate_limit]
    selected_clusters.sort(
        key=lambda cluster: (
            cluster["earliest_time"],
            -(
                sum(float(item.get("relevance_score") or 0.0) for item in cluster["items"])
                / max(len(cluster["items"]), 1)
            ),
        )
    )

    events: list[WorkflowEvent] = []
    for index, cluster in enumerate(selected_clusters, start=1):
        source_seen: set[str] = set()
        source_payloads: list[dict[str, Any]] = []
        for item in sorted(
            cluster["items"],
            key=lambda current: (
                -float(current.get("relevance_score") or 0.0),
                parse_datetime(current["timestamp"]).timestamp(),
            ),
        ):
            signature = source_item_signature(
                text=item["text"],
                source=item["source"],
                timestamp=item["timestamp"],
                url=item.get("url"),
            )
            if signature in source_seen:
                continue
            source_seen.add(signature)
            source_payloads.append(
                {
                    "id": item["id"],
                    "source": item["source"],
                    "author": item.get("author") or item["source"],
                    "text": item["text"],
                    "timestamp": item["timestamp"],
                    "url": item.get("url"),
                }
            )

        if not source_payloads:
            continue

        lead_item = source_payloads[0]
        descriptions = [shorten(payload["text"], 110) for payload in source_payloads[:3]]
        description = descriptions[0]
        if len(descriptions) > 1:
            description = f"{descriptions[0]} Supporting reports: {'; '.join(descriptions[1:])}"

        entity_counts: dict[str, int] = defaultdict(int)
        topic_counts: dict[str, int] = defaultdict(int)
        sentiment_values: list[float] = []
        relevance_values: list[float] = []
        for item in cluster["items"]:
            for entity in item.get("entities", []):
                if entity:
                    entity_counts[entity] += 1
            for topic in item.get("topic_tags", []):
                if topic:
                    topic_counts[topic] += 1
            if isinstance(item.get("sentiment_score"), (int, float)):
                sentiment_values.append(float(item["sentiment_score"]))
            if isinstance(item.get("relevance_score"), (int, float)):
                relevance_values.append(float(item["relevance_score"]))

        entities = [
            label
            for label, _ in sorted(
                entity_counts.items(),
                key=lambda current: (-current[1], -len(current[0]), current[0]),
            )[:5]
        ]
        topic_tags = [
            label
            for label, _ in sorted(
                topic_counts.items(),
                key=lambda current: (-current[1], -len(current[0]), current[0]),
            )[:4]
        ]
        title = guess_event_title(lead_item["text"])
        stack_key = choose_event_stack_key(entities, topic_tags, f"{title} {description}")
        time_scope = classify_recency_tag(cluster["latest_time"])
        if time_scope not in topic_tags:
            topic_tags = [time_scope, *topic_tags][:5]
        if time_scope in {"context", "historical"}:
            description = f"{time_scope.title()} context · {description}"

        events.append(
            WorkflowEvent(
                id=f"evt-{index}",
                title=title,
                description=description,
                source="multi-source" if len(source_payloads) > 1 else lead_item["source"],
                timestamp=normalize_timestamp(cluster["earliest_time"]),
                url=lead_item.get("url"),
                source_count=len(source_payloads),
                sources=source_payloads[:5],
                stack_key=stack_key,
                sentiment_score=(
                    round(sum(sentiment_values) / len(sentiment_values), 4)
                    if sentiment_values
                    else None
                ),
                relevance_score=(
                    round(sum(relevance_values) / len(relevance_values), 4)
                    if relevance_values
                    else None
                ),
                topic_tags=topic_tags,
                entities=entities,
                time_scope=time_scope,
            )
        )

    if not query:
        return events[:max_events]

    for event in events:
        event.relevance_score = score_event_query_relevance(query, event)

    ranked_events = sorted(
        events,
        key=lambda event: (
            float(event.relevance_score or 0.0),
            event.source_count,
            parse_datetime(event.timestamp).timestamp(),
        ),
        reverse=True,
    )
    relevant_events = [
        event for event in ranked_events if float(event.relevance_score or 0.0) >= EVENT_MIN_RELEVANCE_SCORE
    ]
    minimum_keep = min(max_events, 4)
    if len(relevant_events) < minimum_keep:
        relevant_events = ranked_events[:max_events]
    else:
        relevant_events = relevant_events[:max_events]

    relevant_events.sort(key=lambda event: parse_datetime(event.timestamp))
    return relevant_events


def score_event_prediction_support(event: WorkflowEvent, prediction: Prediction) -> float:
    prediction_text = prediction_haystack(prediction)
    prediction_tokens = set(
        important_text_tokens(f"{prediction.question} {prediction.category or ''}", min_length=3, limit=12)
    )
    event_tokens = set(
        important_text_tokens(
            " ".join(
                [
                    event.title,
                    event.description,
                    " ".join(event.entities),
                    " ".join(event.topic_tags),
                ]
            ),
            min_length=3,
            limit=14,
        )
    )
    token_overlap = len(event_tokens & prediction_tokens)
    phrase_hits = 0
    for entity in event.entities:
        normalized_entity = normalize_key(entity)
        if len(normalized_entity) >= 4 and normalized_entity in prediction_text:
            phrase_hits += 1
    if event.stack_key and event.stack_key in prediction_text:
        phrase_hits += 1
    if prediction.category and normalize_key(prediction.category) in normalize_key(
        " ".join(event.topic_tags)
    ):
        phrase_hits += 1

    return round(token_overlap * 2.5 + phrase_hits * 3 + float(event.relevance_score or 0.0) * 2, 4)


def build_affinity_cache_key(
    event_title: str,
    event_description: str,
    prediction_id: str,
) -> str:
    return "||".join(
        [
            normalize_key(event_title),
            normalize_key(event_description),
            prediction_id,
        ]
    )


def finalize_event_prediction_links(
    events: list[WorkflowEvent],
    raw_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    event_lookup = {event.id: event for event in events}
    deduped: dict[tuple[str, str], dict[str, Any]] = {}

    for link in raw_links:
        event_id = str(link.get("event_id") or "")
        prediction_id = str(link.get("prediction_id") or "")
        if event_id not in event_lookup or not prediction_id:
            continue

        key = (event_id, prediction_id)
        current = deduped.get(key)
        if current is None or float(link.get("score") or 0.0) > float(current.get("score") or 0.0):
            deduped[key] = link

    ranked_links = sorted(
        deduped.values(),
        key=lambda link: (
            float(link.get("score") or 0.0),
            float(link.get("magnitude") or 0.0),
            float(link.get("embedding_similarity") or 0.0),
            parse_datetime(event_lookup[link["event_id"]].timestamp).timestamp(),
        ),
        reverse=True,
    )

    prediction_counts: dict[str, int] = defaultdict(int)
    event_counts: dict[str, int] = defaultdict(int)
    final_links: list[dict[str, Any]] = []
    for link in ranked_links:
        if prediction_counts[link["prediction_id"]] >= 8:
            continue
        if event_counts[link["event_id"]] >= 4:
            continue
        final_links.append(link)
        prediction_counts[link["prediction_id"]] += 1
        event_counts[link["event_id"]] += 1

    final_links.sort(key=lambda link: parse_datetime(event_lookup[link["event_id"]].timestamp))
    support_map: dict[str, list[str]] = defaultdict(list)
    for link in final_links:
        support_map[link["event_id"]].append(link["prediction_id"])

    for event in events:
        event.support_prediction_ids = support_map.get(event.id, [])

    return final_links


def prioritize_workflow_predictions(
    predictions: list[Prediction],
    event_prediction_links: list[dict[str, Any]],
    *,
    limit: int,
) -> tuple[list[Prediction], list[dict[str, Any]]]:
    if not predictions:
        return [], []

    link_count_by_prediction: dict[str, int] = defaultdict(int)
    link_score_by_prediction: dict[str, float] = defaultdict(float)
    for link in event_prediction_links:
        prediction_id = str(link.get("prediction_id") or "")
        if not prediction_id:
            continue
        link_count_by_prediction[prediction_id] += 1
        link_score_by_prediction[prediction_id] += float(link.get("score") or 0.0)

    ranked = sorted(
        predictions,
        key=lambda prediction: (
            link_count_by_prediction.get(prediction.id, 0),
            link_score_by_prediction.get(prediction.id, 0.0),
            prediction_popularity_score(prediction),
            float(prediction.relevance_score or 0.0),
            float(prediction.volume_usd or 0.0),
            float(prediction.liquidity_usd or 0.0),
        ),
        reverse=True,
    )

    top_predictions = ranked[:limit]
    allowed_ids = {prediction.id for prediction in top_predictions}
    filtered_links = [
        link for link in event_prediction_links if str(link.get("prediction_id") or "") in allowed_ids
    ]
    return top_predictions, filtered_links


def apply_prediction_support_to_events(
    events: list[WorkflowEvent],
    event_prediction_links: list[dict[str, Any]],
) -> None:
    support_map: dict[str, list[str]] = defaultdict(list)
    for link in event_prediction_links:
        event_id = str(link.get("event_id") or "")
        prediction_id = str(link.get("prediction_id") or "")
        if not event_id or not prediction_id:
            continue
        support_map[event_id].append(prediction_id)

    for event in events:
        event.support_prediction_ids = support_map.get(event.id, [])


def build_event_prediction_links(
    events: list[WorkflowEvent],
    predictions: list[Prediction],
    *,
    candidate_pairs: list[dict[str, Any]] | None = None,
    affinity_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    prediction_lookup = {prediction.id: prediction for prediction in predictions}
    candidate_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    affinity_lookup: dict[tuple[str, str], dict[str, Any]] = {}

    for pair in candidate_pairs or []:
        event_id = str(pair.get("event_id") or "")
        prediction_id = str(pair.get("prediction_id") or "")
        if event_id and prediction_id:
            candidate_lookup[(event_id, prediction_id)] = pair

    for result in affinity_results or []:
        event_id = str(result.get("event_id") or "")
        prediction_id = str(result.get("prediction_id") or "")
        if event_id and prediction_id:
            affinity_lookup[(event_id, prediction_id)] = result

    raw_links: list[dict[str, Any]] = []
    for event in events:
        scoped_predictions: list[Prediction] = []
        scoped_prediction_ids = {
            prediction_id
            for event_id, prediction_id in candidate_lookup
            if event_id == event.id
        }
        if scoped_prediction_ids:
            for prediction_id in scoped_prediction_ids:
                prediction = prediction_lookup.get(prediction_id)
                if prediction is not None:
                    scoped_predictions.append(prediction)
        else:
            scoped_predictions = predictions

        scored_predictions = sorted(
            (
                (score_event_prediction_support(event, prediction), prediction)
                for prediction in scoped_predictions
            ),
            key=lambda item: item[0],
            reverse=True,
        )

        for lexical_score, prediction in scored_predictions[:6]:
            key = (event.id, prediction.id)
            candidate = candidate_lookup.get(key)
            affinity = affinity_lookup.get(key)
            embedding_similarity = float(candidate.get("embedding_similarity") or 0.0) if candidate else 0.0
            magnitude = float(affinity.get("magnitude") or 0.0) if affinity else 0.0
            direction = float(affinity.get("direction") or 0.0) if affinity else 0.0
            reasoning = str(affinity.get("reasoning") or "").strip() if affinity else ""

            composite_score = (
                lexical_score
                + float(event.relevance_score or 0.0) * 3
                + embedding_similarity * 12
                + magnitude * 16
                + abs(direction) * 3
            )
            if affinity and magnitude < 0.18 and lexical_score < 4.5:
                continue
            if not affinity and embedding_similarity < 0.38 and lexical_score < 5.5:
                continue
            if composite_score < 7.5:
                continue

            raw_links.append(
                {
                    "event_id": event.id,
                    "prediction_id": prediction.id,
                    "score": round(composite_score, 4),
                    "lexical_score": round(lexical_score, 4),
                    "embedding_similarity": round(embedding_similarity, 4) if embedding_similarity else None,
                    "magnitude": round(magnitude, 4) if affinity else None,
                    "direction": round(direction, 4) if affinity else None,
                    "reasoning": reasoning or None,
                }
            )

    return finalize_event_prediction_links(events, raw_links)


def build_post_collection_jobs(
    query: str,
    *,
    include_social: bool,
    bluesky_seconds: int,
    existing_posts: list[SourcedPost] | None = None,
) -> tuple[list[tuple[str, Any]], list[str], list[str]]:
    warnings: list[str] = []
    coroutines: list[tuple[str, Any]] = []
    news_terms = build_news_search_terms(query, existing_posts)
    hn_terms = news_terms[:HACKERNEWS_TERM_LIMIT]

    if data_google_news is None:
        if GOOGLE_NEWS_IMPORT_ERROR:
            warnings.append(f"google_news unavailable: {GOOGLE_NEWS_IMPORT_ERROR}")
    else:
        for term in news_terms:
            coroutines.append(
                (
                    f"google_news:{term}",
                    data_google_news.fetch(term, max_results=NEWS_RESULTS_PER_TERM),
                )
            )

    if include_social:
        if data_bluesky_stream is None:
            if BLUESKY_IMPORT_ERROR:
                warnings.append(f"bluesky unavailable: {BLUESKY_IMPORT_ERROR}")
        else:
            social_query = build_social_keyword_query(query, existing_posts)
            coroutines.append(
                (
                    "bluesky",
                    data_bluesky_stream.fetch(
                        social_query,
                        duration_seconds=bluesky_seconds,
                    ),
                )
            )

    for term in hn_terms:
        coroutines.append(
            (
                f"hackernews:{term}",
                fetch_hackernews_posts(term, max_results=HACKERNEWS_RESULTS_PER_TERM),
            )
        )

    coroutines.append(("rss", fetch_rss_posts(query)))
    coroutines.append(("reddit", fetch_reddit_posts(query)))

    return coroutines, warnings, news_terms


async def collect_posts(
    query: str,
    *,
    include_social: bool,
    bluesky_seconds: int,
    existing_posts: list[SourcedPost] | None = None,
) -> tuple[list[SourcedPost], list[str], list[str]]:
    coroutines, warnings, news_terms = build_post_collection_jobs(
        query,
        include_social=include_social,
        bluesky_seconds=bluesky_seconds,
        existing_posts=existing_posts,
    )

    results = await asyncio.gather(
        *(coroutine for _, coroutine in coroutines),
        return_exceptions=True,
    )

    posts: list[SourcedPost] = []

    for (label, _), result in zip(coroutines, results):
        if isinstance(result, Exception):
            warnings.append(f"{label} fetch failed: {result}")
            continue

        for item in result:
            post = normalize_source_post(item)
            if post is None:
                continue
            posts.append(post)

    live_posts = merge_posts([posts])
    cached_posts: list[SourcedPost] = []
    try:
        store_posts_in_cache(query, live_posts)
        cached_posts = load_cached_posts(query)
    except Exception as exc:
        warnings.append(f"source cache unavailable: {exc}")
    return merge_posts([live_posts, cached_posts]), warnings, news_terms


def fallback_events_from_posts(
    posts: list[SourcedPost],
    max_events: int,
    query: str | None = None,
) -> list[WorkflowEvent]:
    return synthesize_events(posts, [], max_events, query=query)


def build_bridge_stub(
    posts: list[SourcedPost],
    max_events: int,
    query: str | None = None,
) -> dict[str, Any]:
    return {
        "available": False,
        "enriched_items": [],
        "events": fallback_events_from_posts(posts, max_events, query=query),
        "event_prediction_links": [],
        "candidate_pairs": [],
        "affinity_results": [],
        "warnings": [],
    }


def warm_sentiment_tree_models() -> list[str]:
    warnings: list[str] = []
    try:
        from pipeline.config import PipelineConfig
        from pipeline.embedder import Embedder
        from pipeline.sentiment_scorer import SentimentScorer
        from pipeline.tagger import Tagger

        config = PipelineConfig()
        Embedder(config).model
        SentimentScorer("Will this warmup succeed?", config).classifier
        Tagger(config).nlp
    except Exception as exc:
        warnings.append(f"sentiment-tree warmup failed: {exc}")
    return warnings


def run_sentiment_tree_bridge(
    request: WorkflowRequest,
    posts: list[SourcedPost],
    predictions: list[Prediction],
) -> dict[str, Any]:
    result = build_bridge_stub(posts, request.max_descendants, request.query)
    analysis_posts = select_analysis_posts(request.query, posts, MAX_ANALYSIS_POSTS)

    if not analysis_posts:
        result["warnings"].append("No source posts were available for sentiment-tree processing.")
        return result

    try:
        from pipeline.config import PipelineConfig
        from pipeline.models import Event as PipelineEvent
        from pipeline.models import EventSource, Prediction as PipelinePrediction, RawItem
        from pipeline.pipeline import Pipeline
    except Exception as exc:
        result["warnings"].append(f"sentiment-tree unavailable in current environment: {exc}")
        return result

    result["available"] = True
    config = PipelineConfig(
        relevance_threshold=request.relevance_threshold,
        affinity_embedding_threshold=request.affinity_threshold,
    )

    raw_items = [
        RawItem(
            text=post.text,
            source=post.source,
            timestamp=parse_datetime(post.timestamp),
            url=post.url or "",
        )
        for post in analysis_posts
    ]

    try:
        pipe = Pipeline(request.query, config=config)
        enriched_items = pipe.process(raw_items, store=False)
    except Exception as exc:
        result["warnings"].append(f"sentiment-tree processing failed: {exc}")
        return result

    result["enriched_items"] = [
        {
            "text": item.text,
            "source": item.source,
            "timestamp": normalize_timestamp(item.timestamp),
            "url": item.url,
            "sentiment_score": item.sentiment_score,
            "sentiment_confidence": item.sentiment_confidence,
            "topic_tags": item.topic_tags,
            "entities": item.entities,
            "relevance_score": item.relevance_score,
        }
        for item in enriched_items
    ]
    result["events"] = synthesize_events(
        analysis_posts,
        result["enriched_items"],
        request.max_descendants,
        query=request.query,
    )
    if not result["events"]:
        result["events"] = fallback_events_from_posts(
            analysis_posts,
            request.max_descendants,
            request.query,
        )
    result["event_prediction_links"] = build_event_prediction_links(result["events"], predictions)

    if not result["events"] or not predictions:
        return result

    try:
        from pipeline.affinity_pipeline import AffinityPipeline
    except Exception as exc:
        result["warnings"].append(f"affinity pipeline unavailable: {exc}")
        return result

    pipeline_events = [
        PipelineEvent(
            Title=event.title,
            Description=event.description,
            Sources=[
                EventSource(
                    Source=str(source.get("source") or event.source),
                    Link=str(source.get("url") or event.url or ""),
                    Summary=str(source.get("text") or source.get("summary") or event.description),
                )
                for source in (event.sources[:5] or [{"source": event.source, "url": event.url, "text": event.description}])
            ],
            ID=index,
        )
        for index, event in enumerate(result["events"], start=1)
    ]

    pipeline_predictions = [
        PipelinePrediction(
            id=prediction.id,
            source=prediction.source,
            question=prediction.question,
            category=prediction.category or "general",
            yes_probability=prediction.yes_probability if prediction.yes_probability is not None else 0.5,
            no_probability=prediction.no_probability if prediction.no_probability is not None else 0.5,
            volume_usd=prediction.volume_usd if prediction.volume_usd is not None else 0.0,
            liquidity_usd=prediction.liquidity_usd if prediction.liquidity_usd is not None else 0.0,
            closes_at=parse_datetime(prediction.closes_at),
            url=prediction.url or "",
        )
        for prediction in predictions
    ]

    try:
        affinity_pipe = AffinityPipeline(config)
        candidates = affinity_pipe.stage1(pipeline_events, pipeline_predictions)
    except Exception as exc:
        result["warnings"].append(f"affinity candidate generation failed: {exc}")
        return result

    workflow_event_id_by_pipeline_id = {
        pipeline_event.ID: workflow_event.id
        for pipeline_event, workflow_event in zip(pipeline_events, result["events"])
    }
    pipeline_event_lookup = {pipeline_event.ID: pipeline_event for pipeline_event in pipeline_events}
    similarity_lookup: dict[tuple[int, str], float] = {}
    for event, prediction, similarity in candidates:
        similarity_lookup[(event.ID, prediction.id)] = similarity

    result["candidate_pairs"] = [
        {
            "event_id": workflow_event_id_by_pipeline_id.get(event.ID, str(event.ID)),
            "prediction_id": prediction.id,
            "event_title": event.Title,
            "prediction_question": prediction.question,
            "embedding_similarity": round(similarity, 4),
        }
        for event, prediction, similarity in candidates
    ]

    if not request.run_llm_affinity or not candidates:
        result["event_prediction_links"] = build_event_prediction_links(
            result["events"],
            predictions,
            candidate_pairs=result["candidate_pairs"],
        )
        return result

    llm_results: list[dict[str, Any]] = []
    uncached_candidates: list[tuple[Any, Any, float]] = []
    for event, prediction, similarity in candidates:
        cache_key = build_affinity_cache_key(event.Title, event.Description, prediction.id)
        cached = LLM_AFFINITY_CACHE.get(cache_key)
        workflow_event_id = workflow_event_id_by_pipeline_id.get(event.ID, str(event.ID))
        if cached is not None:
            llm_results.append(
                {
                    "event_id": workflow_event_id,
                    "prediction_id": prediction.id,
                    "event_title": event.Title,
                    "prediction_question": prediction.question,
                    "embedding_similarity": round(similarity, 4),
                    "direction": round(float(cached.get("direction") or 0.0), 4),
                    "magnitude": round(float(cached.get("magnitude") or 0.0), 4),
                    "reasoning": str(cached.get("reasoning") or ""),
                }
            )
            continue
        if len(uncached_candidates) < AFFINITY_LLM_MAX_CANDIDATES:
            uncached_candidates.append((event, prediction, similarity))

    try:
        for raw_result in affinity_pipe.stream(uncached_candidates):
            event_id = int(raw_result.get("event_id") or 0)
            prediction_id = str(raw_result.get("prediction_id") or "")
            similarity = similarity_lookup.get((event_id, prediction_id), 0.0)
            workflow_event_id = workflow_event_id_by_pipeline_id.get(event_id, str(event_id))
            pipeline_event = pipeline_event_lookup.get(event_id)
            event_title = str(raw_result.get("event_title") or (pipeline_event.Title if pipeline_event else ""))
            event_description = pipeline_event.Description if pipeline_event else ""
            reasoning = str(raw_result.get("reasoning") or "")
            cached_payload = {
                "direction": float(raw_result.get("direction") or 0.0),
                "magnitude": float(raw_result.get("magnitude") or 0.0),
                "reasoning": reasoning,
            }
            LLM_AFFINITY_CACHE[
                build_affinity_cache_key(event_title, event_description, prediction_id)
            ] = cached_payload
            llm_results.append(
                {
                    "event_id": workflow_event_id,
                    "prediction_id": prediction_id,
                    "event_title": event_title,
                    "prediction_question": str(raw_result.get("prediction_question") or ""),
                    "embedding_similarity": round(similarity, 4),
                    "direction": round(cached_payload["direction"], 4),
                    "magnitude": round(cached_payload["magnitude"], 4),
                    "reasoning": reasoning,
                }
            )
    except Exception as exc:
        result["warnings"].append(f"affinity LLM stage failed: {exc}")
        result["affinity_results"] = llm_results
        result["event_prediction_links"] = build_event_prediction_links(
            result["events"],
            predictions,
            candidate_pairs=result["candidate_pairs"],
            affinity_results=result["affinity_results"],
        )
        return result

    result["affinity_results"] = sorted(
        llm_results,
        key=lambda item: (
            float(item.get("magnitude") or 0.0),
            float(item.get("embedding_similarity") or 0.0),
        ),
        reverse=True,
    )
    result["event_prediction_links"] = build_event_prediction_links(
        result["events"],
        predictions,
        candidate_pairs=result["candidate_pairs"],
        affinity_results=result["affinity_results"],
    )
    return result


def build_graph_payload(
    *,
    query: str,
    fetched_at: str,
    posts: list[SourcedPost],
    predictions: list[Prediction],
    events: list[WorkflowEvent],
    event_prediction_links: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_events = sorted(events, key=lambda event: parse_datetime(event.timestamp))

    event_nodes = [
        {
            "id": event.id,
            "data": {
                "label": event.title,
                "category": "event",
                "sentiment": event.sentiment_score if event.sentiment_score is not None else 0.5,
                "source": event.source,
                "timestamp": event.timestamp,
                "summary": (
                    f"{event.time_scope.title()} · {event.source_count} sources · {event.description}"
                    if event.time_scope
                    else f"{event.source_count} sources · {event.description}"
                    if event.source_count
                    else event.description
                ),
                "stackKey": event.stack_key or "general",
                "sourceCount": event.source_count,
                "supportPredictionIds": event.support_prediction_ids,
                "timeScope": event.time_scope,
            },
        }
        for event in ordered_events
    ]

    root_node = {
        "id": "root",
        "data": {
            "label": query,
            "category": "root",
            "sentiment": 0.5,
            "source": "search",
            "timestamp": fetched_at,
            "summary": (
                f"{len(posts)} sourced posts, {len(predictions)} matching predictions, "
                f"{len(events)} graph events."
            ),
        },
    }

    prediction_nodes = [
        {
            "id": prediction.id,
            "data": {
                "label": shorten(prediction.question, 80),
                "category": "prediction",
                "sentiment": prediction.yes_probability if prediction.yes_probability is not None else 0.5,
                "source": prediction.source,
                "timestamp": prediction.closes_at or fetched_at,
                "summary": (
                    f"{(prediction.category or 'general').title()} · YES "
                    f"{round((prediction.yes_probability or 0.5) * 100):.0f}% · "
                    f"Vol ${format_compact_number(prediction.volume_usd)} · "
                    f"Liq ${format_compact_number(prediction.liquidity_usd)}"
                ),
            },
        }
        for prediction in predictions
    ]

    nodes = [root_node, *event_nodes, *prediction_nodes]

    edges: list[dict[str, str]] = []
    edge_seen: set[tuple[str, str]] = set()

    def add_edge(source: str, target: str) -> None:
        key = (source, target)
        if key in edge_seen:
            return
        edge_seen.add(key)
        edges.append({"id": f"e-{source}-{target}", "source": source, "target": target})

    if event_nodes:
        add_edge("root", event_nodes[0]["id"])
    for index in range(len(event_nodes) - 1):
        add_edge(event_nodes[index]["id"], event_nodes[index + 1]["id"])

    for prediction in predictions:
        add_edge("root", prediction.id)

    support_edges = [
        {
            "id": f"support-{link['event_id']}-{link['prediction_id']}",
            "source": link["event_id"],
            "target": link["prediction_id"],
            "relation": "support",
            **{key: value for key, value in link.items() if key not in {"event_id", "prediction_id"}},
        }
        for link in event_prediction_links
    ]
    prediction_event_map: dict[str, list[str]] = defaultdict(list)
    for link in event_prediction_links:
        prediction_event_map[link["prediction_id"]].append(link["event_id"])

    return {
        "nodes": nodes,
        "edges": edges,
        "support_edges": support_edges,
        "prediction_event_map": dict(prediction_event_map),
    }


def build_workflow_payload(
    request: WorkflowRequest,
    posts: list[SourcedPost],
    predictions: list[Prediction],
    prediction_source: str,
    bridge_result: dict[str, Any],
    warnings: list[str],
    stream_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fetched_at = utc_now_iso()
    events = bridge_result["events"]
    graph = build_graph_payload(
        query=request.query,
        fetched_at=fetched_at,
        posts=posts,
        predictions=predictions,
        events=events,
        event_prediction_links=bridge_result["event_prediction_links"],
    )

    posts_by_source: dict[str, int] = defaultdict(int)
    for post in posts:
        posts_by_source[post.source] += 1

    return {
        "query": request.query,
        "fetched_at": fetched_at,
        "snapshot_id": snapshot_token(),
        "source_mode": prediction_source,
        "warnings": warnings,
        "stream": stream_state or {},
        "runtime": {
            "shared_python_env": str(PROJECT_ROOT / ".venv"),
            "sentiment_tree_available": bridge_result["available"],
            "llm_affinity_ran": bool(request.run_llm_affinity and bridge_result["affinity_results"]),
            "startup_preload_ok": not bool(getattr(app.state, "startup_warnings", [])),
        },
        "summary": {
            "posts": len(posts),
            "posts_by_source": dict(posts_by_source),
            "predictions": len(predictions),
            "events": len(events),
            "enriched_items": len(bridge_result["enriched_items"]),
            "candidate_pairs": len(bridge_result["candidate_pairs"]),
            "affinity_results": len(bridge_result["affinity_results"]),
            "event_prediction_links": len(bridge_result["event_prediction_links"]),
        },
        "sources": {
            "posts": [serialize_post(post) for post in posts],
            "predictions": [serialize_prediction(prediction) for prediction in predictions],
            "events": [serialize_event(event) for event in events],
            "enriched_items": bridge_result["enriched_items"],
            "event_prediction_links": bridge_result["event_prediction_links"],
            "candidate_pairs": bridge_result["candidate_pairs"],
            "affinity_results": bridge_result["affinity_results"],
        },
        "graph": graph,
    }


async def execute_workflow(request: WorkflowRequest) -> dict[str, Any]:
    posts, source_warnings, news_terms = await collect_posts(
        request.query,
        include_social=request.include_social,
        bluesky_seconds=request.bluesky_seconds,
    )
    market_search_terms = build_market_search_terms(request.query, posts)
    predictions, prediction_source = await search_predictions(
        SearchRequest(
            query=request.query,
            limit=request.prediction_limit,
            include_closed=request.include_closed,
        ),
        search_terms=market_search_terms,
    )
    bridge_result = await asyncio.to_thread(run_sentiment_tree_bridge, request, posts, predictions)
    prioritized_predictions, prioritized_links = prioritize_workflow_predictions(
        predictions,
        bridge_result["event_prediction_links"],
        limit=request.prediction_limit,
    )
    predictions = prioritized_predictions
    bridge_result["event_prediction_links"] = prioritized_links
    apply_prediction_support_to_events(
        bridge_result["events"],
        bridge_result["event_prediction_links"],
    )

    startup_warnings = list(getattr(app.state, "startup_warnings", []))
    warnings = [*startup_warnings, *source_warnings, *bridge_result["warnings"]]
    return build_workflow_payload(
        request=request,
        posts=posts,
        predictions=predictions,
        prediction_source=prediction_source,
        bridge_result=bridge_result,
        warnings=warnings,
        stream_state={
            "mode": "single",
            "iteration": 1,
            "news_terms": news_terms,
            "market_search_terms": market_search_terms,
        },
    )


def build_streaming_response(request: SearchRequest) -> StreamingResponse:
    async def event_stream():
        yield ndjson_line(
            {
                "type": "status",
                "status": "started",
                "query": request.query,
                "requested_limit": request.limit,
                "fetched_at": utc_now_iso(),
            }
        )

        try:
            predictions, source = await search_predictions(request)
        except Exception as exc:
            yield ndjson_line(
                {
                    "type": "error",
                    "message": str(exc),
                    "fetched_at": utc_now_iso(),
                }
            )
            return

        yield ndjson_line(
            {
                "type": "status",
                "status": "results_ready",
                "source_mode": source,
                "count": len(predictions),
                "fetched_at": utc_now_iso(),
            }
        )

        for index, prediction in enumerate(predictions, start=1):
            yield ndjson_line(
                {
                    "type": "prediction",
                    "index": index,
                    "data": serialize_prediction(prediction),
                }
            )
            await asyncio.sleep(0)

        yield ndjson_line(
            {
                "type": "complete",
                "query": request.query,
                "count": len(predictions),
                "fetched_at": utc_now_iso(),
            }
        )

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def build_workflow_streaming_response(request: WorkflowRequest) -> StreamingResponse:
    async def event_stream():
        startup_warnings = list(getattr(app.state, "startup_warnings", []))
        yield ndjson_line(
            {
                "type": "status",
                "status": "started",
                "query": request.query,
                "fetched_at": utc_now_iso(),
            }
        )
        yield ndjson_line(
            {
                "type": "snapshot",
                "stage": "initial",
                "data": build_workflow_payload(
                    request=request,
                    posts=[],
                    predictions=[],
                    prediction_source="pending",
                    bridge_result=build_bridge_stub([], request.max_descendants, request.query),
                    warnings=startup_warnings,
                    stream_state={"mode": "stream", "stage": "initial", "iteration": 0},
                ),
            }
        )

        source_jobs, source_warnings, news_terms = build_post_collection_jobs(
            request.query,
            include_social=request.include_social,
            bluesky_seconds=request.bluesky_seconds,
        )
        posts: list[SourcedPost] = []
        source_warnings_combined = [*startup_warnings, *source_warnings]

        yield ndjson_line(
            {
                "type": "status",
                "status": "sources_started",
                "jobs": len(source_jobs),
                "news_terms": news_terms,
                "fetched_at": utc_now_iso(),
            }
        )

        if source_jobs:
            async def run_source_job(label: str, coroutine: Any) -> tuple[str, Any, Exception | None]:
                try:
                    return label, await coroutine, None
                except Exception as exc:  # pragma: no cover - passthrough for stream status
                    return label, [], exc

            source_tasks = [
                asyncio.create_task(run_source_job(label, coroutine))
                for label, coroutine in source_jobs
            ]
            for completed_task in asyncio.as_completed(source_tasks):
                label, result, source_error = await completed_task
                if source_error is not None:
                    exc = source_error
                    source_warnings.append(f"{label} fetch failed: {exc}")
                    source_warnings_combined = [*startup_warnings, *source_warnings]
                    yield ndjson_line(
                        {
                            "type": "status",
                            "status": "source_batch_failed",
                            "label": label,
                            "warnings": [f"{label} fetch failed: {exc}"],
                            "posts": len(posts),
                            "fetched_at": utc_now_iso(),
                        }
                    )
                    continue

                batch_posts: list[SourcedPost] = []
                for item in result:
                    post = normalize_source_post(item)
                    if post is None:
                        continue
                    batch_posts.append(post)

                previous_post_count = len(posts)
                posts = merge_posts([posts, batch_posts])
                new_posts = max(len(posts) - previous_post_count, 0)
                source_bridge = build_bridge_stub(posts, request.max_descendants, request.query)

                yield ndjson_line(
                    {
                        "type": "status",
                        "status": "source_batch",
                        "label": label,
                        "new_posts": new_posts,
                        "posts": len(posts),
                        "warnings": source_warnings,
                        "fetched_at": utc_now_iso(),
                    }
                )
                yield ndjson_line(
                    {
                        "type": "snapshot",
                        "stage": "sources",
                        "data": build_workflow_payload(
                            request=request,
                            posts=posts,
                            predictions=[],
                            prediction_source="pending",
                            bridge_result=source_bridge,
                            warnings=source_warnings_combined,
                            stream_state={
                                "mode": "stream",
                                "stage": "sources",
                                "iteration": 1,
                                "news_terms": news_terms,
                                "source_batch_label": label,
                                "new_posts": new_posts,
                            },
                        ),
                    }
                )

        try:
            store_posts_in_cache(request.query, posts)
            cached_posts = load_cached_posts(request.query)
        except Exception as exc:
            source_warnings.append(f"source cache unavailable: {exc}")
            source_warnings_combined = [*startup_warnings, *source_warnings]
            cached_posts = []

        if cached_posts:
            live_post_keys = {post_dedupe_key(post) for post in posts}
            cached_only_count = sum(
                1 for post in cached_posts if post_dedupe_key(post) not in live_post_keys
            )
            posts = merge_posts([posts, cached_posts])
            yield ndjson_line(
                {
                    "type": "status",
                    "status": "historical_context_loaded",
                    "posts": len(posts),
                    "historical_posts": cached_only_count,
                    "fetched_at": utc_now_iso(),
                }
            )

        source_bridge = build_bridge_stub(posts, request.max_descendants, request.query)
        yield ndjson_line(
            {
                "type": "status",
                "status": "sources_collected",
                "posts": len(posts),
                "warnings": source_warnings,
                "news_terms": news_terms,
                "fetched_at": utc_now_iso(),
            }
        )
        yield ndjson_line(
            {
                "type": "snapshot",
                "stage": "sources",
                "data": build_workflow_payload(
                    request=request,
                    posts=posts,
                    predictions=[],
                    prediction_source="pending",
                    bridge_result=source_bridge,
                    warnings=source_warnings_combined,
                    stream_state={
                        "mode": "stream",
                        "stage": "sources",
                        "iteration": 1,
                        "news_terms": news_terms,
                    },
                ),
            }
        )

        market_search_terms = build_market_search_terms(request.query, posts)
        predictions, prediction_source = await search_predictions(
            SearchRequest(
                query=request.query,
                limit=request.prediction_limit,
                include_closed=request.include_closed,
            ),
            search_terms=market_search_terms,
        )
        yield ndjson_line(
            {
                "type": "status",
                "status": "predictions_ready",
                "source_mode": prediction_source,
                "predictions": len(predictions),
                "market_search_terms": market_search_terms,
                "fetched_at": utc_now_iso(),
            }
        )
        yield ndjson_line(
            {
                "type": "snapshot",
                "stage": "predictions",
                "data": build_workflow_payload(
                    request=request,
                    posts=posts,
                    predictions=predictions,
                    prediction_source=prediction_source,
                    bridge_result=source_bridge,
                    warnings=source_warnings_combined,
                    stream_state={
                        "mode": "stream",
                        "stage": "predictions",
                        "iteration": 1,
                        "news_terms": news_terms,
                        "market_search_terms": market_search_terms,
                    },
                ),
            }
        )

        bridge_result = await asyncio.to_thread(run_sentiment_tree_bridge, request, posts, predictions)
        predictions, bridge_result["event_prediction_links"] = prioritize_workflow_predictions(
            predictions,
            bridge_result["event_prediction_links"],
            limit=request.prediction_limit,
        )
        apply_prediction_support_to_events(
            bridge_result["events"],
            bridge_result["event_prediction_links"],
        )
        yield ndjson_line(
            {
                "type": "status",
                "status": "sentiment_tree_complete",
                "available": bridge_result["available"],
                "events": len(bridge_result["events"]),
                "enriched_items": len(bridge_result["enriched_items"]),
                "candidate_pairs": len(bridge_result["candidate_pairs"]),
                "affinity_results": len(bridge_result["affinity_results"]),
                "warnings": bridge_result["warnings"],
                "fetched_at": utc_now_iso(),
            }
        )

        payload = build_workflow_payload(
            request=request,
            posts=posts,
            predictions=predictions,
            prediction_source=prediction_source,
            bridge_result=bridge_result,
            warnings=[
                *source_warnings_combined,
                *bridge_result["warnings"],
            ],
            stream_state={
                "mode": "stream",
                "stage": "complete",
                "iteration": 1,
                "news_terms": news_terms,
                "market_search_terms": market_search_terms,
            },
        )
        yield ndjson_line(
            {
                "type": "snapshot",
                "stage": "complete",
                "data": payload,
            }
        )
        yield ndjson_line(
            {
                "type": "complete",
                "query": request.query,
                "fetched_at": utc_now_iso(),
            }
        )

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def sleep_with_disconnect_check(
    duration_seconds: int,
    client_request: FastAPIRequest,
) -> bool:
    if duration_seconds <= 0:
        return not await client_request.is_disconnected()

    remaining = float(duration_seconds)
    while remaining > 0:
        if await client_request.is_disconnected():
            return False
        chunk = min(0.5, remaining)
        await asyncio.sleep(chunk)
        remaining -= chunk
    return not await client_request.is_disconnected()


def build_live_workflow_streaming_response(
    request: LiveWorkflowRequest,
    client_request: FastAPIRequest,
) -> StreamingResponse:
    async def event_stream():
        startup_warnings = list(getattr(app.state, "startup_warnings", []))
        try:
            accumulated_posts = load_cached_posts(request.query)
        except Exception as exc:
            startup_warnings.append(f"source cache unavailable: {exc}")
            accumulated_posts = []
        accumulated_predictions: list[Prediction] = []
        prediction_source = "pending"

        yield ndjson_line(
            {
                "type": "status",
                "status": "started",
                "mode": "live",
                "query": request.query,
                "poll_interval_seconds": request.poll_interval_seconds,
                "fetched_at": utc_now_iso(),
            }
        )
        yield ndjson_line(
            {
                "type": "snapshot",
                "stage": "initial",
                "data": build_workflow_payload(
                    request=request,
                    posts=accumulated_posts,
                    predictions=[],
                    prediction_source=prediction_source,
                    bridge_result=build_bridge_stub(
                        accumulated_posts,
                        request.max_descendants,
                        request.query,
                    ),
                    warnings=startup_warnings,
                    stream_state={
                        "mode": "live",
                        "stage": "initial",
                        "iteration": 0,
                        "poll_interval_seconds": request.poll_interval_seconds,
                    },
                ),
            }
        )

        iteration = 0
        while True:
            if await client_request.is_disconnected():
                return

            iteration += 1
            yield ndjson_line(
                {
                    "type": "status",
                    "status": "cycle_started",
                    "mode": "live",
                    "iteration": iteration,
                    "query": request.query,
                    "fetched_at": utc_now_iso(),
                }
            )

            existing_post_keys = {post_dedupe_key(post) for post in accumulated_posts}
            seen_post_keys = set(existing_post_keys)
            total_new_posts = 0
            source_jobs, source_warnings, news_terms = build_post_collection_jobs(
                request.query,
                include_social=request.include_social,
                bluesky_seconds=request.bluesky_seconds,
                existing_posts=accumulated_posts,
            )
            source_warnings_combined = [*startup_warnings, *source_warnings]
            cycle_live_posts: list[SourcedPost] = []
            yield ndjson_line(
                {
                    "type": "status",
                    "status": "sources_started",
                    "mode": "live",
                    "iteration": iteration,
                    "jobs": len(source_jobs),
                    "news_terms": news_terms,
                    "posts": len(accumulated_posts),
                    "fetched_at": utc_now_iso(),
                }
            )

            if source_jobs:
                async def run_source_job(label: str, coroutine: Any) -> tuple[str, Any, Exception | None]:
                    try:
                        return label, await coroutine, None
                    except Exception as exc:  # pragma: no cover - passthrough for stream status
                        return label, [], exc

                source_tasks = [
                    asyncio.create_task(run_source_job(label, coroutine))
                    for label, coroutine in source_jobs
                ]
                for completed_task in asyncio.as_completed(source_tasks):
                    label, result, source_error = await completed_task
                    if source_error is not None:
                        source_warnings.append(f"{label} fetch failed: {source_error}")
                        source_warnings_combined = [*startup_warnings, *source_warnings]
                        yield ndjson_line(
                            {
                                "type": "status",
                                "status": "source_batch_failed",
                                "mode": "live",
                                "iteration": iteration,
                                "label": label,
                                "warnings": [f"{label} fetch failed: {source_error}"],
                                "posts": len(accumulated_posts),
                                "fetched_at": utc_now_iso(),
                            }
                        )
                        continue

                    batch_posts: list[SourcedPost] = []
                    batch_new_posts = 0
                    for item in result:
                        post = normalize_source_post(item)
                        if post is None:
                            continue
                        batch_posts.append(post)
                        key = post_dedupe_key(post)
                        if key not in seen_post_keys:
                            seen_post_keys.add(key)
                            batch_new_posts += 1

                    if batch_posts:
                        cycle_live_posts = merge_posts([cycle_live_posts, batch_posts])
                        accumulated_posts = merge_posts([accumulated_posts, batch_posts])
                        total_new_posts += batch_new_posts

                    source_bridge = build_bridge_stub(
                        accumulated_posts,
                        request.max_descendants,
                        request.query,
                    )
                    yield ndjson_line(
                        {
                            "type": "status",
                            "status": "source_batch",
                            "mode": "live",
                            "iteration": iteration,
                            "label": label,
                            "new_posts": batch_new_posts,
                            "total_new_posts": total_new_posts,
                            "posts": len(accumulated_posts),
                            "warnings": source_warnings,
                            "fetched_at": utc_now_iso(),
                        }
                    )
                    yield ndjson_line(
                        {
                            "type": "snapshot",
                            "stage": "sources",
                            "data": build_workflow_payload(
                                request=request,
                                posts=accumulated_posts,
                                predictions=accumulated_predictions,
                                prediction_source=prediction_source,
                                bridge_result=source_bridge,
                                warnings=source_warnings_combined,
                                stream_state={
                                    "mode": "live",
                                    "stage": "sources",
                                    "iteration": iteration,
                                    "new_posts": total_new_posts,
                                    "latest_source_batch_posts": batch_new_posts,
                                    "poll_interval_seconds": request.poll_interval_seconds,
                                    "news_terms": news_terms,
                                    "source_batch_label": label,
                                },
                            ),
                        }
                    )

            try:
                store_posts_in_cache(request.query, cycle_live_posts)
                cached_posts = load_cached_posts(request.query)
            except Exception as exc:
                source_warnings.append(f"source cache unavailable: {exc}")
                source_warnings_combined = [*startup_warnings, *source_warnings]
                cached_posts = []

            if cached_posts:
                live_post_keys = {post_dedupe_key(post) for post in accumulated_posts}
                cached_only_posts = [
                    post for post in cached_posts if post_dedupe_key(post) not in live_post_keys
                ]
                if cached_only_posts:
                    cached_only_count = len(cached_only_posts)
                    accumulated_posts = merge_posts([accumulated_posts, cached_only_posts])
                    total_new_posts += cached_only_count
                    yield ndjson_line(
                        {
                            "type": "status",
                            "status": "historical_context_loaded",
                            "mode": "live",
                            "iteration": iteration,
                            "posts": len(accumulated_posts),
                            "historical_posts": cached_only_count,
                            "total_new_posts": total_new_posts,
                            "fetched_at": utc_now_iso(),
                        }
                    )

            source_bridge = build_bridge_stub(
                accumulated_posts,
                request.max_descendants,
                request.query,
            )
            yield ndjson_line(
                {
                    "type": "status",
                    "status": "sources_collected",
                    "mode": "live",
                    "iteration": iteration,
                    "posts": len(accumulated_posts),
                    "new_posts": total_new_posts,
                    "news_terms": news_terms,
                    "warnings": source_warnings,
                    "fetched_at": utc_now_iso(),
                }
            )
            yield ndjson_line(
                {
                    "type": "snapshot",
                    "stage": "sources",
                    "data": build_workflow_payload(
                        request=request,
                        posts=accumulated_posts,
                        predictions=accumulated_predictions,
                        prediction_source=prediction_source,
                        bridge_result=source_bridge,
                        warnings=source_warnings_combined,
                        stream_state={
                            "mode": "live",
                            "stage": "sources",
                            "iteration": iteration,
                            "new_posts": total_new_posts,
                            "poll_interval_seconds": request.poll_interval_seconds,
                            "news_terms": news_terms,
                        },
                    ),
                }
            )

            market_search_terms = build_market_search_terms(request.query, accumulated_posts)
            existing_prediction_keys = {
                prediction_dedupe_key(prediction) for prediction in accumulated_predictions
            }
            cycle_predictions, prediction_source = await search_predictions(
                SearchRequest(
                    query=request.query,
                    limit=request.prediction_limit,
                    include_closed=request.include_closed,
                ),
                search_terms=market_search_terms,
            )
            new_predictions_count = sum(
                1
                for prediction in cycle_predictions
                if prediction_dedupe_key(prediction) not in existing_prediction_keys
            )
            accumulated_predictions = rank_predictions(
                request.query,
                merge_predictions([accumulated_predictions, cycle_predictions]),
                search_terms=market_search_terms,
            )[: request.prediction_limit]

            yield ndjson_line(
                {
                    "type": "status",
                    "status": "predictions_ready",
                    "mode": "live",
                    "iteration": iteration,
                    "source_mode": prediction_source,
                    "predictions": len(accumulated_predictions),
                    "new_predictions": new_predictions_count,
                    "market_search_terms": market_search_terms,
                    "fetched_at": utc_now_iso(),
                }
            )
            yield ndjson_line(
                {
                    "type": "snapshot",
                    "stage": "predictions",
                    "data": build_workflow_payload(
                        request=request,
                        posts=accumulated_posts,
                        predictions=accumulated_predictions,
                        prediction_source=prediction_source,
                        bridge_result=source_bridge,
                        warnings=source_warnings_combined,
                        stream_state={
                            "mode": "live",
                            "stage": "predictions",
                            "iteration": iteration,
                            "new_posts": total_new_posts,
                            "new_predictions": new_predictions_count,
                            "poll_interval_seconds": request.poll_interval_seconds,
                            "news_terms": news_terms,
                            "market_search_terms": market_search_terms,
                        },
                    ),
                }
            )

            bridge_result = await asyncio.to_thread(
                run_sentiment_tree_bridge,
                request,
                accumulated_posts,
                accumulated_predictions,
            )
            accumulated_predictions, bridge_result["event_prediction_links"] = prioritize_workflow_predictions(
                accumulated_predictions,
                bridge_result["event_prediction_links"],
                limit=request.prediction_limit,
            )
            apply_prediction_support_to_events(
                bridge_result["events"],
                bridge_result["event_prediction_links"],
            )
            warnings = [
                *source_warnings_combined,
                *bridge_result["warnings"],
            ]
            payload = build_workflow_payload(
                request=request,
                posts=accumulated_posts,
                predictions=accumulated_predictions,
                prediction_source=prediction_source,
                bridge_result=bridge_result,
                warnings=warnings,
                stream_state={
                    "mode": "live",
                    "stage": "analysis",
                    "iteration": iteration,
                    "new_posts": total_new_posts,
                    "new_predictions": new_predictions_count,
                    "poll_interval_seconds": request.poll_interval_seconds,
                    "news_terms": news_terms,
                    "market_search_terms": market_search_terms,
                },
            )
            yield ndjson_line(
                {
                    "type": "status",
                    "status": "cycle_complete",
                    "mode": "live",
                    "iteration": iteration,
                    "posts": payload["summary"]["posts"],
                    "predictions": payload["summary"]["predictions"],
                    "events": payload["summary"]["events"],
                    "fetched_at": utc_now_iso(),
                }
            )
            yield ndjson_line(
                {
                    "type": "snapshot",
                    "stage": "analysis",
                    "data": payload,
                }
            )

            should_continue = await sleep_with_disconnect_check(
                request.poll_interval_seconds,
                client_request,
            )
            if not should_continue:
                return

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "tree-hacks-api",
        "search_endpoint": "/predictions/search",
        "search_stream_endpoint": "/predictions/search/stream",
        "workflow_endpoint": "/workflow/run",
        "workflow_stream_endpoint": "/workflow/run/stream",
        "workflow_live_stream_endpoint": "/workflow/live/stream",
    }


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "timestamp": utc_now_iso()}


@app.get("/search/suggestions")
async def search_suggestions_get(
    query: str = Query(..., min_length=1),
    limit: int = Query(8, ge=1, le=12),
) -> JSONResponse:
    return JSONResponse(await build_search_suggestions(query, limit=limit))


@app.get("/predictions/search")
async def search_predictions_get(
    query: str = Query(..., min_length=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    include_closed: bool = False,
) -> JSONResponse:
    request = SearchRequest(query=query, limit=limit, include_closed=include_closed)
    predictions, source = await search_predictions(request)
    return JSONResponse(
        {
            "query": request.query,
            "fetched_at": utc_now_iso(),
            "source_mode": source,
            "predictions": [serialize_prediction(prediction) for prediction in predictions],
        }
    )


@app.post("/predictions/search")
async def search_predictions_post(request: SearchRequest) -> JSONResponse:
    predictions, source = await search_predictions(request)
    return JSONResponse(
        {
            "query": request.query,
            "fetched_at": utc_now_iso(),
            "source_mode": source,
            "predictions": [serialize_prediction(prediction) for prediction in predictions],
        }
    )


@app.get("/predictions/search/stream")
async def search_predictions_stream_get(
    query: str = Query(..., min_length=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    include_closed: bool = False,
) -> StreamingResponse:
    request = SearchRequest(query=query, limit=limit, include_closed=include_closed)
    return build_streaming_response(request)


@app.post("/predictions/search/stream")
async def search_predictions_stream_post(request: SearchRequest) -> StreamingResponse:
    return build_streaming_response(request)


@app.get("/workflow/run")
async def workflow_run_get(
    query: str = Query(..., min_length=1),
    prediction_limit: int = Query(DEFAULT_WORKFLOW_PREDICTION_LIMIT, ge=1, le=MAX_LIMIT),
    include_closed: bool = False,
    include_social: bool = True,
    bluesky_seconds: int = Query(3, ge=0, le=20),
    max_descendants: int = Query(DEFAULT_WORKFLOW_DESCENDANTS, ge=1, le=MAX_WORKFLOW_DESCENDANTS),
    relevance_threshold: float = Query(0.55, ge=0.0, le=1.0),
    affinity_threshold: float = Query(0.50, ge=0.0, le=1.0),
    run_llm_affinity: bool = DEFAULT_RUN_LLM_AFFINITY,
) -> JSONResponse:
    request = WorkflowRequest(
        query=query,
        prediction_limit=prediction_limit,
        include_closed=include_closed,
        include_social=include_social,
        bluesky_seconds=bluesky_seconds,
        max_descendants=max_descendants,
        relevance_threshold=relevance_threshold,
        affinity_threshold=affinity_threshold,
        run_llm_affinity=run_llm_affinity,
    )
    return JSONResponse(await execute_workflow(request))


@app.post("/workflow/run")
async def workflow_run_post(request: WorkflowRequest) -> JSONResponse:
    return JSONResponse(await execute_workflow(request))


@app.get("/workflow/run/stream")
async def workflow_run_stream_get(
    query: str = Query(..., min_length=1),
    prediction_limit: int = Query(DEFAULT_WORKFLOW_PREDICTION_LIMIT, ge=1, le=MAX_LIMIT),
    include_closed: bool = False,
    include_social: bool = True,
    bluesky_seconds: int = Query(3, ge=0, le=20),
    max_descendants: int = Query(DEFAULT_WORKFLOW_DESCENDANTS, ge=1, le=MAX_WORKFLOW_DESCENDANTS),
    relevance_threshold: float = Query(0.55, ge=0.0, le=1.0),
    affinity_threshold: float = Query(0.50, ge=0.0, le=1.0),
    run_llm_affinity: bool = DEFAULT_RUN_LLM_AFFINITY,
) -> StreamingResponse:
    request = WorkflowRequest(
        query=query,
        prediction_limit=prediction_limit,
        include_closed=include_closed,
        include_social=include_social,
        bluesky_seconds=bluesky_seconds,
        max_descendants=max_descendants,
        relevance_threshold=relevance_threshold,
        affinity_threshold=affinity_threshold,
        run_llm_affinity=run_llm_affinity,
    )
    return build_workflow_streaming_response(request)


@app.post("/workflow/run/stream")
async def workflow_run_stream_post(request: WorkflowRequest) -> StreamingResponse:
    return build_workflow_streaming_response(request)


@app.get("/workflow/live/stream")
async def workflow_live_stream_get(
    client_request: FastAPIRequest,
    query: str = Query(..., min_length=1),
    prediction_limit: int = Query(DEFAULT_WORKFLOW_PREDICTION_LIMIT, ge=1, le=MAX_LIMIT),
    include_closed: bool = False,
    include_social: bool = True,
    bluesky_seconds: int = Query(3, ge=0, le=20),
    max_descendants: int = Query(DEFAULT_WORKFLOW_DESCENDANTS, ge=1, le=MAX_WORKFLOW_DESCENDANTS),
    relevance_threshold: float = Query(0.55, ge=0.0, le=1.0),
    affinity_threshold: float = Query(0.50, ge=0.0, le=1.0),
    run_llm_affinity: bool = DEFAULT_RUN_LLM_AFFINITY,
    poll_interval_seconds: int = Query(
        DEFAULT_LIVE_POLL_INTERVAL_SECONDS,
        ge=LIVE_POLL_MIN_SECONDS,
        le=LIVE_POLL_MAX_SECONDS,
    ),
) -> StreamingResponse:
    workflow_request = LiveWorkflowRequest(
        query=query,
        prediction_limit=prediction_limit,
        include_closed=include_closed,
        include_social=include_social,
        bluesky_seconds=bluesky_seconds,
        max_descendants=max_descendants,
        relevance_threshold=relevance_threshold,
        affinity_threshold=affinity_threshold,
        run_llm_affinity=run_llm_affinity,
        poll_interval_seconds=poll_interval_seconds,
    )
    return build_live_workflow_streaming_response(workflow_request, client_request)


@app.post("/workflow/live/stream")
async def workflow_live_stream_post(
    client_request: FastAPIRequest,
    workflow_request: LiveWorkflowRequest,
) -> StreamingResponse:
    return build_live_workflow_streaming_response(workflow_request, client_request)
