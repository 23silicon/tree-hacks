from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field


GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
DEFAULT_LIMIT = 10
MAX_LIMIT = 25
REQUEST_TIMEOUT_SECONDS = 12.0
SAMPLE_DATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "sentiment-tree"
    / "polymarket_preds.json"
)


app = FastAPI(
    title="Tree Hacks Polymarket API",
    version="0.1.0",
    description=(
        "Searches Polymarket-related predictions and exposes both standard "
        "JSON and streaming NDJSON endpoints."
    ),
)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Question, topic, or event")
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    include_closed: bool = Field(
        False, description="Whether to include closed markets from the upstream feed"
    )


class Prediction(BaseModel):
    id: str
    source: str
    question: str
    category: str | None = None
    yes_probability: float | None = None
    no_probability: float | None = None
    volume_usd: float | None = None
    liquidity_usd: float | None = None
    closes_at: str | None = None
    url: str | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token}


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


def normalize_prediction(item: dict[str, Any]) -> Prediction | None:
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
        category=choose_category(item),
        yes_probability=yes_probability,
        no_probability=no_probability,
        volume_usd=item.get("volume_usd") or item.get("volume") or item.get("volumeNum"),
        liquidity_usd=(
            item.get("liquidity_usd") or item.get("liquidity") or item.get("liquidityNum")
        ),
        closes_at=str(closes_at) if closes_at else None,
        url=market_url(item),
    )


def score_prediction(query: str, prediction: Prediction) -> float:
    query_text = query.strip().lower()
    query_tokens = tokenize(query_text)
    if not query_tokens:
        return 0.0

    haystack_parts = [prediction.question]
    if prediction.category:
        haystack_parts.append(prediction.category)
    if prediction.url:
        haystack_parts.append(prediction.url)

    haystack = " ".join(haystack_parts).lower()
    haystack_tokens = tokenize(haystack)

    overlap = len(query_tokens & haystack_tokens)
    if overlap == 0 and query_text not in haystack:
        return 0.0

    score = float(overlap * 10)
    if query_text in haystack:
        score += 25
    if prediction.volume_usd:
        score += min(float(prediction.volume_usd) / 1_000_000, 5)
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
        prediction = normalize_prediction(item)
        if prediction is not None:
            predictions.append(prediction)
    return predictions


async def fetch_live_polymarket_predictions(
    *,
    query: str,
    include_closed: bool,
) -> list[Prediction]:
    params = {
        "limit": 250,
        "offset": 0,
        "archived": "false",
    }
    if not include_closed:
        params["active"] = "true"
        params["closed"] = "false"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(GAMMA_MARKETS_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, list):
        raise ValueError("Unexpected Polymarket response format")

    predictions = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        item["source"] = "polymarket"
        prediction = normalize_prediction(item)
        if prediction is not None:
            predictions.append(prediction)

    return rank_predictions(query, predictions)


def rank_predictions(query: str, predictions: list[Prediction]) -> list[Prediction]:
    scored: list[tuple[float, Prediction]] = []
    seen_ids: set[str] = set()

    for prediction in predictions:
        if prediction.id in seen_ids:
            continue
        seen_ids.add(prediction.id)

        score = score_prediction(query, prediction)
        if score > 0:
            scored.append((score, prediction))

    scored.sort(
        key=lambda item: (
            item[0],
            item[1].volume_usd or 0,
            item[1].liquidity_usd or 0,
        ),
        reverse=True,
    )
    return [prediction for _, prediction in scored]


async def search_predictions(request: SearchRequest) -> tuple[list[Prediction], str]:
    try:
        live_predictions = await fetch_live_polymarket_predictions(
            query=request.query,
            include_closed=request.include_closed,
        )
        if live_predictions:
            return live_predictions[: request.limit], "live"
    except Exception:
        live_predictions = []

    fallback_predictions = rank_predictions(request.query, parse_sample_predictions())
    return fallback_predictions[: request.limit], "sample"


def serialize_prediction(prediction: Prediction) -> dict[str, Any]:
    return prediction.model_dump(exclude_none=True)


def ndjson_line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "tree-hacks-polymarket-api",
        "stream_endpoint": "/predictions/search/stream",
        "search_endpoint": "/predictions/search",
    }


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "timestamp": utc_now_iso()}


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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
