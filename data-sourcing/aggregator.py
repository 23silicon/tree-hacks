"""
AGGREGATOR — 自动发现热门话题，按话题聚类数据，推送给前端

两种模式：
1. LLM模式（需要ANTHROPIC_API_KEY）— Claude Haiku自动发现和分类话题
2. 关键词模式（无需API）— 纯词频分析发现话题

输出: 通过broadcast推送 type="topics" 消息给前端
"""
import asyncio
import json
import time
import os
import re
from collections import Counter
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Try to import anthropic, fallback to keyword mode if not available
try:
    from anthropic import AsyncAnthropic
    HAS_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if HAS_ANTHROPIC:
        anthropic_client = AsyncAnthropic()
except ImportError:
    HAS_ANTHROPIC = False

STOP_WORDS = {
    'the', 'a', 'an', 'in', 'on', 'of', 'to', 'for', 'and', 'is', 'as', 'at',
    'by', 'with', 'from', 'its', 'has', 'that', 'it', 'are', 'was', 'be', 'this',
    'but', 'not', 'or', 'have', 'will', 'been', 'up', 'out', 'how', 'what', 'who',
    'says', 'could', 'may', 'into', 'after', 'about', 'over', 'since', 'than', 'his',
    'their', 'they', 'more', 'new', 'first', 'last', 'us', 'he', 'she', 'we', 'all',
    'can', 'would', 'which', 'do', 'if', 'no', 'so', 'my', 'just', 'also', 'most',
    'now', 'like', 'other', 'some', 'even', 'many', 'these', 'had', 'get', 'got',
    'one', 'two', 'three', 'year', 'years', 'day', 'days', 'week', 'month', 'time',
    'people', 'said', 'very', 'when', 'why', 'here', 'being', 'between', 'where',
    'those', 'through', 'during', 'each', 'before', 'should', 'still', 'well',
    'because', 'any', 'both', 'such', 'much', 'while', 'does', 'going', 'our',
    'them', 'then', 'way', 'own', 'back', 'only', 'come', 'made', 'did', 'take',
    'make', 'world', 'news', 'live', 'updates', 'latest', 'says', 'report',
}

CATEGORIES = {
    'military': ['war', 'strike', 'attack', 'missile', 'troops', 'military', 'bomb',
                 'drone', 'navy', 'army', 'combat', 'weapon', 'defense', 'invasion',
                 'houthi', 'marines', 'airbase', 'aircraft', 'carrier'],
    'politics': ['trump', 'biden', 'congress', 'gop', 'democrat', 'republican', 'election',
                 'vote', 'senate', 'house', 'political', 'president', 'governor', 'poll',
                 'campaign', 'maga', 'liberal', 'conservative', 'party', 'lawmaker'],
    'diplomatic': ['talks', 'diplomacy', 'allies', 'negotiate', 'ceasefire', 'peace',
                   'summit', 'un', 'nato', 'treaty', 'sanction', 'ambassador', 'diplomatic',
                   'agreement', 'deal', 'resolution'],
    'economic': ['oil', 'gas', 'fuel', 'price', 'market', 'stock', 'economy', 'trade',
                 'dollar', 'inflation', 'tariff', 'shipping', 'supply', 'debt', 'gdp',
                 'recession', 'cost', 'billion', 'trillion'],
    'social': ['protest', 'rally', 'meme', 'viral', 'opinion', 'poll', 'sentiment',
               'public', 'reaction', 'community', 'movement', 'march', 'nokings'],
    'humanitarian': ['civilian', 'casualty', 'refugee', 'aid', 'crisis', 'death',
                     'hospital', 'evacuation', 'humanitarian', 'victim', 'injured'],
}


# ============================================================
# KEYWORD-BASED TOPIC DISCOVERY (no API needed)
# ============================================================

def extract_phrases(text: str) -> list[str]:
    """Extract meaningful 1-2 word phrases from text."""
    words = re.findall(r'[a-zA-Z\']+', text.lower())
    phrases = []
    for w in words:
        if w not in STOP_WORDS and len(w) > 2:
            phrases.append(w)
    # Also extract bigrams
    for i in range(len(words) - 1):
        if words[i] not in STOP_WORDS and words[i+1] not in STOP_WORDS:
            if len(words[i]) > 2 and len(words[i+1]) > 2:
                phrases.append(f"{words[i]} {words[i+1]}")
    return phrases


def categorize(keywords: list[str]) -> str:
    """Determine category based on keywords."""
    scores = {cat: 0 for cat in CATEGORIES}
    for kw in keywords:
        kw_lower = kw.lower()
        for cat, cat_words in CATEGORIES.items():
            if any(cw in kw_lower for cw in cat_words):
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def discover_topics_keyword(all_data: list[dict], max_topics: int = 10) -> list[dict]:
    """
    Discover topics using keyword frequency analysis.
    No API key needed.
    """
    # Collect all text
    all_phrases = []
    for item in all_data:
        text = item.get("text", "") or item.get("question", "")
        all_phrases.extend(extract_phrases(text))

    # Count phrase frequency
    phrase_counts = Counter(all_phrases)

    # Remove overly common phrases (> 30% of items = too generic)
    threshold = len(all_data) * 0.3
    phrase_counts = {p: c for p, c in phrase_counts.items() if c < threshold and c >= 3}

    # Group related phrases into topics
    # Start with the most frequent phrase, grab related items, repeat
    used_phrases = set()
    topics = []

    sorted_phrases = sorted(phrase_counts.items(), key=lambda x: -x[1])

    for phrase, count in sorted_phrases:
        if phrase in used_phrases:
            continue
        if len(topics) >= max_topics:
            break

        # Find all items containing this phrase
        matching_items = []
        matching_ids = set()
        phrase_lower = phrase.lower()

        for item in all_data:
            text = (item.get("text", "") or item.get("question", "")).lower()
            if phrase_lower in text and item.get("id") not in matching_ids:
                matching_items.append(item)
                matching_ids.add(item.get("id"))

        if len(matching_items) < 3:
            continue

        # Find related phrases in these items
        related_phrases = []
        related_counts = Counter()
        for item in matching_items:
            text = item.get("text", "") or ""
            for p in extract_phrases(text):
                if p != phrase and p not in used_phrases:
                    related_counts[p] += 1

        keywords = [phrase] + [p for p, c in related_counts.most_common(5) if c >= 2]
        used_phrases.update(keywords)

        # Calculate source diversity
        sources = {}
        for item in matching_items:
            s = item.get("source", "unknown")
            sources[s] = sources.get(s, 0) + 1

        # Heat score: item count * source diversity * recency
        source_diversity = len(sources) / max(len(set(i.get("source") for i in all_data)), 1)
        heat = min(1.0, (len(matching_items) / max(len(all_data) * 0.2, 1)) * (1 + source_diversity))

        # Build topic name from top phrase (capitalize)
        topic_name = phrase.title()
        if len(topic_name) < 10:
            # Add second keyword for context
            for kw in keywords[1:]:
                if kw != phrase:
                    topic_name = f"{phrase.title()} — {kw.title()}"
                    break

        category = categorize(keywords)

        # Latest headline
        latest = sorted(matching_items, key=lambda x: x.get("timestamp", ""), reverse=True)
        latest_headline = latest[0].get("text", "")[:120] if latest else ""

        topics.append({
            "id": re.sub(r'[^a-z0-9]+', '-', phrase.lower()).strip('-'),
            "name": topic_name,
            "category": category,
            "heat": round(heat, 2),
            "item_count": len(matching_items),
            "sources": sources,
            "keywords": keywords,
            "latest": latest_headline,
            "item_ids": list(matching_ids)[:50],  # Cap for payload size
        })

    # Sort by heat
    topics.sort(key=lambda t: -t["heat"])
    return topics


# ============================================================
# LLM-BASED TOPIC DISCOVERY (needs ANTHROPIC_API_KEY)
# ============================================================

async def discover_topics_llm(all_data: list[dict], max_topics: int = 10) -> list[dict]:
    """
    Use Claude Haiku to discover and categorize topics.
    More accurate than keyword method, but needs API key.
    """
    # Sample recent headlines
    recent = all_data[:150]
    headlines = []
    for i, item in enumerate(recent):
        text = item.get("text", "") or item.get("question", "")
        source = item.get("source", "?")
        headlines.append(f"[{i}] ({source}) {text[:150]}")

    prompt = f"""Analyze these {len(headlines)} news headlines and social media posts.
Identify the {max_topics} most important distinct topics/stories.

For each topic return a JSON object:
- "name": clear topic name (5-10 words)
- "category": one of [military, politics, diplomatic, economic, social, humanitarian, tech]
- "keywords": list of 3-5 lowercase keywords to match more articles
- "heat": 0.0-1.0 how hot/trending this topic is
- "headline_indices": list of [i] numbers from the input that belong to this topic

Return ONLY a JSON array, no other text.

Headlines:
{chr(10).join(headlines)}"""

    try:
        response = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        raw_topics = json.loads(text)

        # Build full topic objects
        topics = []
        for t in raw_topics[:max_topics]:
            keywords = [kw.lower() for kw in t.get("keywords", [])]

            # Match all items by keywords
            matching_items = []
            matching_ids = set()
            for item in all_data:
                item_text = (item.get("text", "") or item.get("question", "")).lower()
                if any(kw in item_text for kw in keywords):
                    if item.get("id") not in matching_ids:
                        matching_items.append(item)
                        matching_ids.add(item.get("id"))

            sources = {}
            for item in matching_items:
                s = item.get("source", "unknown")
                sources[s] = sources.get(s, 0) + 1

            latest = sorted(matching_items, key=lambda x: x.get("timestamp", ""), reverse=True)
            latest_headline = latest[0].get("text", "")[:120] if latest else ""

            topics.append({
                "id": re.sub(r'[^a-z0-9]+', '-', t.get("name", "").lower()).strip('-'),
                "name": t.get("name", "Unknown Topic"),
                "category": t.get("category", "general"),
                "heat": t.get("heat", 0.5),
                "item_count": len(matching_items),
                "sources": sources,
                "keywords": keywords,
                "latest": latest_headline,
                "item_ids": list(matching_ids)[:50],
            })

        topics.sort(key=lambda t: -t["heat"])
        return topics

    except Exception as e:
        print(f"[AGGREGATOR] LLM error: {e}, falling back to keyword mode")
        return discover_topics_keyword(all_data, max_topics)


# ============================================================
# MAIN AGGREGATOR LOOP
# ============================================================

async def aggregator_loop(all_data: list, broadcast_fn, interval: int = 30):
    """
    Continuous topic discovery and clustering.
    Reads from all_data, pushes topic updates via broadcast_fn.
    """
    print(f"[AGGREGATOR] Starting ({'LLM mode' if HAS_ANTHROPIC else 'keyword mode'})")

    last_count = 0

    while True:
        # Wait for enough data
        if len(all_data) < 10:
            await asyncio.sleep(5)
            continue

        # Only re-analyze if we have new data
        if len(all_data) == last_count:
            await asyncio.sleep(interval)
            continue

        last_count = len(all_data)
        start = time.time()

        try:
            if HAS_ANTHROPIC:
                topics = await discover_topics_llm(all_data)
            else:
                topics = discover_topics_keyword(all_data)

            elapsed = time.time() - start

            if topics:
                await broadcast_fn({
                    "type": "topics",
                    "topics": topics,
                    "mode": "llm" if HAS_ANTHROPIC else "keyword",
                    "data_count": len(all_data),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                })

                # Print summary
                print(f"\n[AGGREGATOR] Discovered {len(topics)} topics ({elapsed:.1f}s):")
                for t in topics[:5]:
                    src_list = ', '.join(f"{s}:{c}" for s, c in sorted(t['sources'].items(), key=lambda x: -x[1])[:3])
                    print(f"  [{t['heat']:.0%}] {t['name']} ({t['item_count']} items, {src_list})")

        except Exception as e:
            print(f"[AGGREGATOR] Error: {e}")

        await asyncio.sleep(interval)


# ============================================================
# ON-DEMAND: 单话题深度分析 + SENTIMENT
# ============================================================

async def analyze_topic_with_sentiment(topic: str, items: list[dict]) -> dict | None:
    """
    对用户搜索的单个话题做深度分析:
    1. 发现子话题
    2. 每条内容做sentiment分析
    3. 生成整体sentiment摘要
    """
    if not items:
        return None

    print(f"[SENTIMENT] Analyzing {len(items)} items for '{topic}'...")
    start = time.time()

    sample = items[:80]
    headlines = []
    for i, item in enumerate(sample):
        text = item.get("text", "") or item.get("question", "")
        source = item.get("source", "?")
        headlines.append(f"[{i}] ({source}) {text[:200]}")

    prompt = f"""Analyze these {len(headlines)} articles/posts about "{topic}".

Do TWO things:

1. TOPIC DISCOVERY: Group into 3-5 sub-topics. For each:
   - "name": sub-topic name
   - "category": politics/sports/economic/social/tech/entertainment
   - "keywords": 3-5 keywords
   - "heat": 0.0-1.0
   - "headline_indices": which [i] belong here

2. SENTIMENT ANALYSIS: For each headline, classify:
   - "sentiment": "positive" / "negative" / "neutral"
   - "score": -1.0 to 1.0
   - "emotion": primary emotion (excitement, concern, anger, hope, humor, etc.)

Return JSON:
{{
  "sub_topics": [...],
  "sentiments": [
    {{"index": 0, "sentiment": "positive", "score": 0.7, "emotion": "excitement"}},
    ...
  ],
  "overall_sentiment": {{
    "score": 0.0,
    "label": "positive/negative/neutral/mixed",
    "summary": "One sentence summary of overall sentiment"
  }}
}}

Only valid JSON, no other text.

Content:
{chr(10).join(headlines)}"""

    try:
        response = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        analysis = json.loads(text)

        elapsed = time.time() - start

        # Build sub-topic objects
        sub_topics = []
        for st in analysis.get("sub_topics", []):
            indices = st.get("headline_indices", [])
            matched = [sample[i] for i in indices if i < len(sample)]
            keywords = [kw.lower() for kw in st.get("keywords", [])]

            for item in items:
                item_text = (item.get("text", "") or "").lower()
                if any(kw in item_text for kw in keywords):
                    if item not in matched:
                        matched.append(item)

            sources = {}
            for item in matched:
                s = item.get("source", "unknown")
                sources[s] = sources.get(s, 0) + 1

            sub_topics.append({
                "id": re.sub(r'[^a-z0-9]+', '-', st.get("name", "").lower()).strip('-'),
                "name": st.get("name", ""),
                "category": st.get("category", "general"),
                "heat": st.get("heat", 0.5),
                "keywords": keywords,
                "item_count": len(matched),
                "sources": sources,
                "latest": matched[0].get("text", "")[:150] if matched else "",
            })

        # Attach sentiment to items
        sentiments = analysis.get("sentiments", [])
        sentiment_scores = []
        for s in sentiments:
            idx = s.get("index", 0)
            if idx < len(sample):
                sample[idx]["sentiment"] = s.get("sentiment", "neutral")
                sample[idx]["sentiment_score"] = s.get("score", 0)
                sample[idx]["emotion"] = s.get("emotion", "unknown")
                sentiment_scores.append(s.get("score", 0))

        overall = analysis.get("overall_sentiment", {})

        result = {
            "type": "topic_analysis",
            "query": topic,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_seconds": round(elapsed, 1),
            "total_items": len(items),
            "analyzed_items": len(sample),
            "sub_topics": sub_topics,
            "overall_sentiment": {
                "score": overall.get("score", sum(sentiment_scores) / max(len(sentiment_scores), 1)),
                "label": overall.get("label", "neutral"),
                "summary": overall.get("summary", ""),
            },
            "sentiment_distribution": {
                "positive": sum(1 for s in sentiments if s.get("sentiment") == "positive"),
                "negative": sum(1 for s in sentiments if s.get("sentiment") == "negative"),
                "neutral": sum(1 for s in sentiments if s.get("sentiment") == "neutral"),
            },
            "items": [
                {
                    "id": item.get("id"),
                    "source": item.get("source"),
                    "author": item.get("author"),
                    "text": item.get("text", "")[:300],
                    "timestamp": item.get("timestamp"),
                    "url": item.get("url"),
                    "sentiment": item.get("sentiment", "neutral"),
                    "sentiment_score": item.get("sentiment_score", 0),
                    "emotion": item.get("emotion", "unknown"),
                }
                for item in sample
            ],
        }

        dist = result["sentiment_distribution"]
        print(f"[SENTIMENT] Done in {elapsed:.1f}s — {topic}")
        print(f"  Overall: {result['overall_sentiment']['label']} ({result['overall_sentiment']['score']:+.2f})")
        print(f"  Distribution: +{dist['positive']} / ={dist['neutral']} / -{dist['negative']}")
        print(f"  Sub-topics: {', '.join(t['name'] for t in sub_topics)}")

        return result

    except Exception as e:
        print(f"[SENTIMENT] Error: {e}")
        return None
