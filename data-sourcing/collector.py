"""
COLLECTOR — 主入口，并行采集所有数据源，输出统一JSON

用法:
    python collector.py "iran war"
    python collector.py "tariffs china"

输出:
    output.json — 队友可以直接用的统一格式数据
"""
import asyncio
import json
import time
import sys
import os

from models import Post, MarketData
import google_news
import bluesky_stream
import polymarket


async def collect(query: str, bluesky_seconds: int = 12) -> dict:
    """
    并行采集所有数据源，返回统一JSON。

    Args:
        query: 搜索话题
        bluesky_seconds: Bluesky监听时长

    Returns:
        dict — 包含所有采集数据的统一格式
    """
    print(f"\n{'='*60}")
    print(f"  HIVEMIND COLLECTOR — Topic: {query}")
    print(f"{'='*60}\n")

    start = time.time()

    # 并行采集三个数据源
    print("[1/3] Launching parallel data collection...\n")

    news_posts, bsky_posts, markets = await asyncio.gather(
        google_news.fetch(query),
        bluesky_stream.fetch(query, duration_seconds=bluesky_seconds),
        polymarket.fetch(query),
    )

    all_posts = news_posts + bsky_posts
    elapsed = time.time() - start

    # 构建输出
    output = {
        "meta": {
            "query": query,
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_seconds": round(elapsed, 1),
            "counts": {
                "google_news": len(news_posts),
                "bluesky": len(bsky_posts),
                "polymarket": len(markets),
                "total_posts": len(all_posts),
            }
        },
        "posts": [p.to_dict() for p in all_posts],
        "markets": [m.to_dict() for m in markets],
    }

    # 保存到文件
    output_path = os.path.join(os.path.dirname(__file__), "output.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # 打印摘要
    print(f"\n{'='*60}")
    print(f"  COLLECTION COMPLETE")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Google News: {len(news_posts)} articles")
    print(f"  Bluesky:     {len(bsky_posts)} posts")
    print(f"  Polymarket:  {len(markets)} markets")
    print(f"  Total:       {len(all_posts)} items")
    print(f"  Output:      {output_path}")
    print(f"{'='*60}\n")

    # 预览前5条
    print("  Top articles:")
    for p in news_posts[:5]:
        print(f"    [{p.author}] {p.text[:70]}")

    if markets:
        print(f"\n  Markets:")
        for m in markets[:3]:
            print(f"    [{m.yes_price:.1%} YES] {m.question[:60]}")

    return output


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "iran war"
    asyncio.run(collect(query))
