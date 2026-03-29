"""
ENRICHMENT — 数据质量提升层

1. 跨源去重 + 多源覆盖计数
2. 来源可信度分级
3. 事件时间线提取
4. 实体提取
5. 矛盾检测

全部输出JSON，队友直接用。
"""
import asyncio
import json
import re
import time
import os
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

try:
    from anthropic import AsyncAnthropic
    HAS_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if HAS_ANTHROPIC:
        anthropic_client = AsyncAnthropic()
except ImportError:
    HAS_ANTHROPIC = False


# ============================================================
# 1. 跨源去重 + 多源覆盖计数
# ============================================================

SOURCE_CREDIBILITY = {
    # T1 — 权威通讯社/大报
    "Reuters World": 1, "reuters.com": 1, "AP News": 1,
    "BBC World": 1, "BBC": 1, "The New York Times": 1, "WSJ": 1,
    "WSJ World": 1, "WSJ Opinion": 1, "The Economist": 1,

    # T2 — 主流媒体
    "CNN Top": 2, "cnn.com": 2, "The Guardian": 2, "Guardian World": 2,
    "The Washington Post": 2, "Politico": 2, "NBC News": 2,
    "CBS News": 2, "ABC News": 2, "NPR News": 2, "NPR": 2,
    "Fox News World": 2, "Fox News Politics": 2, "PBS": 2,
    "Al Jazeera": 2, "The Independent": 2, "The Hill": 2,
    "Time Magazine": 2, "Axios": 2, "Vox": 2, "USA Today": 2,

    # T3 — 二线媒体/专业
    "CNBC": 3, "MarketWatch": 3, "Fortune": 3, "Business Insider": 3,
    "NY Post": 3, "Drudge Report": 3, "Yahoo News": 3,
    "hackernews": 3, "Chatham House": 3,

    # T4 — 社交媒体
    "reddit": 4, "bluesky": 4, "youtube": 4,

    # T5 — 未知
    "google_news": 2,  # Google News聚合的一般都是主流媒体
}


def get_credibility(source: str) -> int:
    """返回来源的可信度等级 (1=最高, 5=未知)"""
    return SOURCE_CREDIBILITY.get(source, SOURCE_CREDIBILITY.get(source.split(":")[0].strip(), 5))


def normalize_text(text: str) -> str:
    """标准化文本用于去重比较"""
    text = text.lower().strip()
    # 去掉来源后缀 "... - CNN", "... | Reuters"
    text = re.sub(r'\s*[-–|]\s*[A-Za-z\s\.]+$', '', text)
    # 去掉标点
    text = re.sub(r'[^\w\s]', '', text)
    # 去掉多余空格
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def compute_similarity(text1: str, text2: str) -> float:
    """快速文本相似度 (词级Jaccard)"""
    words1 = set(normalize_text(text1).split())
    words2 = set(normalize_text(text2).split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def deduplicate(items: list[dict], threshold: float = 0.6) -> list[dict]:
    """
    跨源去重。相似的文章合并成一个，记录多少个源覆盖了。

    返回去重后的items，每个item多了:
    - coverage_count: 多少个源报道了同一事件
    - coverage_sources: 哪些源报道了
    - credibility_tier: 最高可信度等级
    - is_duplicate: False (重复的被移除了)
    """
    if not items:
        return []

    # 只对text字段有值的items做去重
    text_items = [i for i in items if i.get("text")]
    no_text = [i for i in items if not i.get("text")]

    # 按credibility排序，高可信度的优先保留
    text_items.sort(key=lambda x: get_credibility(x.get("source", "unknown")))

    clusters = []  # list of (primary_item, [all_items_in_cluster])

    for item in text_items:
        item_text = item.get("text", "")
        matched = False

        for cluster_primary, cluster_items in clusters:
            if compute_similarity(item_text, cluster_primary.get("text", "")) >= threshold:
                cluster_items.append(item)
                matched = True
                break

        if not matched:
            clusters.append((item, [item]))

    # 构建去重后的结果
    deduped = []
    for primary, cluster_items in clusters:
        sources = list(set(i.get("source", "unknown") for i in cluster_items))
        authors = list(set(i.get("author", "unknown") for i in cluster_items))
        best_tier = min(get_credibility(s) for s in sources)

        enriched = dict(primary)
        enriched["coverage_count"] = len(cluster_items)
        enriched["coverage_sources"] = sources
        enriched["credibility_tier"] = best_tier
        enriched["credibility_label"] = {1: "authoritative", 2: "mainstream", 3: "secondary", 4: "social", 5: "unknown"}.get(best_tier, "unknown")

        # 如果有更权威的版本，用那个的text
        if best_tier < get_credibility(primary.get("source", "unknown")):
            for ci in cluster_items:
                if get_credibility(ci.get("source", "unknown")) == best_tier:
                    enriched["text"] = ci.get("text", enriched["text"])
                    enriched["author"] = ci.get("author", enriched["author"])
                    break

        deduped.append(enriched)

    # 加上没有text的items
    for item in no_text:
        item["coverage_count"] = 1
        item["coverage_sources"] = [item.get("source", "unknown")]
        item["credibility_tier"] = get_credibility(item.get("source", "unknown"))
        deduped.append(item)

    return deduped


# ============================================================
# 3. 事件时间线提取 + 4. 实体提取 + 5. 矛盾检测
# (全部用一个LLM调用完成，节省API成本)
# ============================================================

async def extract_events_entities_contradictions(items: list[dict]) -> dict:
    """
    一次LLM调用提取:
    - 结构化事件时间线
    - 实体 (人名、地名、组织)
    - 矛盾观点

    返回:
    {
        "events": [{date, event, type, sources_count, entities}],
        "entities": {people: [...], places: [...], orgs: [...]},
        "contradictions": [{claim_a, source_a, claim_b, source_b, topic}]
    }
    """
    if not HAS_ANTHROPIC:
        return _extract_basic(items)

    # 取高可信度的items做分析（去重后的，按coverage排序）
    sorted_items = sorted(items, key=lambda x: (-x.get("coverage_count", 1), x.get("credibility_tier", 5)))
    sample = sorted_items[:60]

    headlines = []
    for i, item in enumerate(sample):
        src = item.get("author", item.get("source", "?"))
        text = item.get("text", "")[:200]
        ts = item.get("timestamp", "")
        coverage = item.get("coverage_count", 1)
        headlines.append(f"[{i}] ({src}, {coverage} sources) {text}")

    prompt = f"""Analyze these {len(headlines)} news items. Do THREE things:

1. EVENT TIMELINE: Extract 10-15 key events in chronological order. Each event:
   - "date": ISO date or "unknown"
   - "event": what happened (1 sentence)
   - "type": "escalation" / "de-escalation" / "military" / "diplomatic" / "economic" / "political" / "social"
   - "headline_indices": which [i] are about this event
   - "importance": 1-10

2. ENTITY EXTRACTION: List all named entities across all items:
   - "people": list of person names mentioned
   - "places": list of locations/countries
   - "organizations": list of organizations/groups

3. CONTRADICTION DETECTION: Find claims that DIRECTLY contradict each other:
   - "claim_a": what source A says
   - "source_a": which source
   - "claim_b": what source B says (opposite/contradicting)
   - "source_b": which source
   - "topic": what the disagreement is about

Return JSON:
{{
  "events": [...],
  "entities": {{"people": [...], "places": [...], "organizations": [...]}},
  "contradictions": [...]
}}

Only valid JSON.

Headlines:
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
        result = json.loads(text)

        # Enrich events with source counts
        events = result.get("events", [])
        for evt in events:
            indices = evt.get("headline_indices", [])
            evt["sources_count"] = sum(
                sample[i].get("coverage_count", 1)
                for i in indices if i < len(sample)
            )

        return result

    except Exception as e:
        print(f"[ENRICHMENT] LLM error: {e}")
        return _extract_basic(items)


def _extract_basic(items: list[dict]) -> dict:
    """Fallback: 基础实体提取 (无LLM)"""
    # 简单的大写词提取作为实体
    people = set()
    places = set()
    common_places = {"us", "uk", "iran", "israel", "yemen", "saudi", "china", "russia",
                     "iraq", "syria", "gaza", "middle east", "europe", "asia"}
    common_people = {"trump", "biden", "rubio", "netanyahu", "khamenei", "musk", "putin"}

    for item in items:
        text_lower = (item.get("text", "") or "").lower()
        for p in common_people:
            if p in text_lower:
                people.add(p.title())
        for p in common_places:
            if p in text_lower:
                places.add(p.title())

    return {
        "events": [],
        "entities": {
            "people": list(people),
            "places": list(places),
            "organizations": [],
        },
        "contradictions": [],
    }


# ============================================================
# MAIN: 完整enrichment pipeline
# ============================================================

async def enrich_data(all_data: list[dict], broadcast_fn=None) -> dict:
    """
    完整enrichment pipeline:
    1. 去重 + 覆盖计数
    2. 可信度分级
    3. 事件时间线 + 实体 + 矛盾检测

    返回enriched JSON，也通过broadcast推给前端。
    """
    start = time.time()
    print(f"\n[ENRICHMENT] Processing {len(all_data)} items...")

    # Step 1 & 2: 去重 + 可信度
    deduped = deduplicate(all_data)
    dup_removed = len(all_data) - len(deduped)
    print(f"  Deduplication: {len(all_data)} → {len(deduped)} ({dup_removed} duplicates removed)")

    # 统计可信度分布
    tier_counts = defaultdict(int)
    for item in deduped:
        tier_counts[item.get("credibility_label", "unknown")] += 1
    print(f"  Credibility: " + ", ".join(f"{k}:{v}" for k, v in sorted(tier_counts.items())))

    # 高覆盖事件 (多个源报道的)
    high_coverage = [i for i in deduped if i.get("coverage_count", 1) >= 3]
    print(f"  High coverage (3+ sources): {len(high_coverage)} items")

    # Step 3, 4, 5: 事件 + 实体 + 矛盾 (LLM)
    analysis = await extract_events_entities_contradictions(deduped)

    elapsed = time.time() - start

    result = {
        "type": "enrichment",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(elapsed, 1),
        "stats": {
            "raw_count": len(all_data),
            "deduped_count": len(deduped),
            "duplicates_removed": dup_removed,
            "dedup_ratio": f"{dup_removed/max(len(all_data),1)*100:.1f}%",
            "credibility_distribution": dict(tier_counts),
            "high_coverage_items": len(high_coverage),
        },
        "events": analysis.get("events", []),
        "entities": analysis.get("entities", {}),
        "contradictions": analysis.get("contradictions", []),
        "top_stories": [
            {
                "text": i.get("text", "")[:200],
                "coverage_count": i.get("coverage_count", 1),
                "coverage_sources": i.get("coverage_sources", []),
                "credibility": i.get("credibility_label", "unknown"),
                "source": i.get("source", "?"),
                "author": i.get("author", "?"),
            }
            for i in sorted(deduped, key=lambda x: -x.get("coverage_count", 1))[:20]
        ],
        "deduped_items": [
            {
                "id": i.get("id"),
                "source": i.get("source"),
                "author": i.get("author"),
                "text": i.get("text", "")[:300],
                "timestamp": i.get("timestamp"),
                "url": i.get("url"),
                "coverage_count": i.get("coverage_count", 1),
                "coverage_sources": i.get("coverage_sources", []),
                "credibility_tier": i.get("credibility_tier", 5),
                "credibility_label": i.get("credibility_label", "unknown"),
            }
            for i in deduped[:300]
        ],
    }

    # Print summary
    events = result["events"]
    entities = result["entities"]
    contradictions = result["contradictions"]

    print(f"\n[ENRICHMENT] Done in {elapsed:.1f}s:")
    print(f"  Events: {len(events)}")
    if events:
        for e in events[:5]:
            print(f"    [{e.get('type','?'):12s}] {e.get('event','')[:70]}")
    print(f"  Entities: {len(entities.get('people',[]))} people, {len(entities.get('places',[]))} places, {len(entities.get('organizations',[]))} orgs")
    print(f"  Contradictions: {len(contradictions)}")
    if contradictions:
        for c in contradictions[:3]:
            print(f"    ⚡ {c.get('source_a','?')}: \"{c.get('claim_a','')[:50]}\"")
            print(f"      vs {c.get('source_b','?')}: \"{c.get('claim_b','')[:50]}\"")

    if broadcast_fn:
        await broadcast_fn(result)

    # 保存JSON
    output_path = os.path.join(os.path.dirname(__file__), "enriched_output.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {output_path}")

    return result


async def enrichment_loop(all_data: list, broadcast_fn, interval: int = 60):
    """每60秒跑一次enrichment pipeline"""
    last_count = 0
    while True:
        if len(all_data) < 20:
            await asyncio.sleep(10)
            continue
        if len(all_data) == last_count:
            await asyncio.sleep(interval)
            continue
        last_count = len(all_data)
        try:
            await enrich_data(all_data, broadcast_fn)
        except Exception as e:
            print(f"[ENRICHMENT] Error: {e}")
        await asyncio.sleep(interval)
