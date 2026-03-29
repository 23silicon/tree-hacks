"""
HIVEMIND SDK — Python library for data sourcing + analysis

Usage:
    from hivemind import search, trending, analyze, stream

    # Search any topic → get structured JSON with sentiment
    result = search("no kings protest")
    print(result["overall_sentiment"])

    # Get current trending topics
    topics = trending()

    # Analyze existing data
    analysis = analyze(items)

    # Start live stream (blocking)
    stream("iran war", callback=my_handler)
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from stream_server import (
    scrape_all_news, scrape_all_rss, scrape_reddit, scrape_polymarket,
    scrape_hackernews, scrape_youtube, fetch_google_trends,
    stream_bluesky, broadcast, ALL_DATA, SEEN_IDS,
)
from aggregator import (
    discover_topics_llm, discover_topics_keyword,
    analyze_topic_with_sentiment, HAS_ANTHROPIC,
)
from enrichment import enrich_data, deduplicate, get_credibility
from stream_server import filter_relevant


def _run(coro):
    """Run async function synchronously."""
    try:
        loop = asyncio.get_running_loop()
        # Already in async context, create task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


# ============================================================
# search(query) — 搜索任何话题，返回完整分析+sentiment
# ============================================================

def search(query: str, include_sentiment: bool = True) -> dict:
    """
    Search any topic across all sources.
    Returns structured JSON with items, sub-topics, and sentiment.

    Args:
        query: any topic string, e.g. "no kings protest", "lebron james"
        include_sentiment: if True and API key available, run sentiment analysis

    Returns:
        {
            "query": "...",
            "total_items": 934,
            "items": [{source, text, timestamp, sentiment, score, emotion}, ...],
            "sub_topics": [{name, heat, item_count}, ...],
            "overall_sentiment": {score, label, summary},
            "sentiment_distribution": {positive, negative, neutral},
        }
    """
    async def _search():
        before = len(ALL_DATA)

        await asyncio.gather(
            scrape_all_news(query),
            scrape_all_rss(query),
            scrape_reddit(query),
            scrape_polymarket(query),
            scrape_youtube(query),
        )

        new_items = ALL_DATA[before:]
        relevant = filter_relevant(new_items, query)
        print(f"[search] Collected {len(new_items)}, relevant: {len(relevant)} for '{query}'")

        if include_sentiment and HAS_ANTHROPIC and relevant:
            result = await analyze_topic_with_sentiment(query, relevant)
            if result:
                # Also run enrichment (events, entities, contradictions)
                enrichment = await enrich_data(relevant)
                result["enrichment"] = {
                    "events": enrichment.get("events", []),
                    "entities": enrichment.get("entities", {}),
                    "contradictions": enrichment.get("contradictions", []),
                    "stats": enrichment.get("stats", {}),
                    "top_stories": enrichment.get("top_stories", []),
                }
                return result

        # Fallback: return items without sentiment
        return {
            "query": query,
            "total_items": len(new_items),
            "items": [
                {"id": i.get("id"), "source": i.get("source"), "author": i.get("author"),
                 "text": i.get("text", "")[:300], "timestamp": i.get("timestamp"), "url": i.get("url")}
                for i in new_items[:100]
            ],
        }

    return _run(_search())


# ============================================================
# trending() — 获取当前热门话题
# ============================================================

def trending() -> dict:
    """
    Discover trending topics from Google Trends + current data.

    Returns:
        {
            "google_trends": ["topic1", "topic2", ...],
            "discovered_topics": [{name, heat, category, item_count}, ...],
        }
    """
    async def _trending():
        trends = await fetch_google_trends()

        if ALL_DATA and len(ALL_DATA) >= 10:
            if HAS_ANTHROPIC:
                topics = await discover_topics_llm(ALL_DATA)
            else:
                topics = discover_topics_keyword(ALL_DATA)
        else:
            topics = []

        return {
            "google_trends": trends,
            "discovered_topics": topics,
        }

    return _run(_trending())


# ============================================================
# analyze(items) — 对已有数据做深度分析
# ============================================================

def analyze(items: list[dict] = None, query: str = "general") -> dict:
    """
    Analyze existing data: dedup, entities, events, contradictions.

    Args:
        items: list of item dicts (if None, uses all collected data)
        query: topic label

    Returns:
        {
            "stats": {raw_count, deduped_count, ...},
            "events": [{date, event, type}, ...],
            "entities": {people, places, organizations},
            "contradictions": [{claim_a, source_a, claim_b, source_b}, ...],
        }
    """
    async def _analyze():
        data = items or ALL_DATA
        if not data:
            return {"error": "No data to analyze. Run search() first."}
        return await enrich_data(data)

    return _run(_analyze())


# ============================================================
# collect(query) — 只采集数据，不做分析
# ============================================================

def collect(query: str, bluesky_seconds: int = 5) -> list[dict]:
    """
    Collect data from all sources without analysis.

    Args:
        query: search topic
        bluesky_seconds: how long to listen to Bluesky firehose

    Returns:
        list of item dicts
    """
    async def _collect():
        before = len(ALL_DATA)

        await asyncio.gather(
            scrape_all_news(query),
            scrape_all_rss(query),
            scrape_reddit(query),
            scrape_polymarket(query),
            scrape_hackernews(),
            scrape_youtube(query),
            stream_bluesky(query, duration=bluesky_seconds),
        )

        return ALL_DATA[before:]

    return _run(_collect())


# ============================================================
# sentiment(text_or_items) — 对文本或items做sentiment分析
# ============================================================

def sentiment(query: str, items: list[dict] = None) -> dict:
    """
    Run sentiment analysis on items.

    Args:
        query: topic label
        items: list of item dicts (if None, collects first)

    Returns:
        topic_analysis dict with sentiment per item
    """
    async def _sentiment():
        data = items
        if not data:
            data = await asyncio.gather(scrape_all_news(query))
            data = ALL_DATA[-100:]

        if HAS_ANTHROPIC:
            return await analyze_topic_with_sentiment(query, data)
        return {"error": "ANTHROPIC_API_KEY required for sentiment analysis"}

    return _run(_sentiment())


# ============================================================
# save(data, filename) — 保存到JSON
# ============================================================

def save(data: dict, filename: str = "output.json"):
    """Save data dict to JSON file."""
    path = os.path.join(os.path.dirname(__file__), filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved: {path}")
    return path


# ============================================================
# Quick test
# ============================================================

if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "iran war"

    print(f"=== Hivemind SDK Test: '{topic}' ===\n")

    result = search(topic)

    print(f"\nTotal items: {result.get('total_items', '?')}")

    if "overall_sentiment" in result:
        s = result["overall_sentiment"]
        print(f"Sentiment: {s['label']} ({s['score']:+.2f})")
        print(f"Summary: {s['summary']}")

    if "sub_topics" in result:
        print(f"\nSub-topics:")
        for t in result["sub_topics"]:
            print(f"  [{t['heat']:.0%}] {t['name']} ({t['item_count']} items)")

    save(result, f"topic_{topic.replace(' ', '_')}.json")
