"""
Bluesky JetStream — 实时社交媒体firehose
完全免费，无需认证，WebSocket连接
实时过滤所有Bluesky帖子中包含关键词的内容
"""
import asyncio
import json
from datetime import datetime, timezone
import websockets
from models import Post

JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"


async def fetch(query: str, duration_seconds: int = 15, max_posts: int = 100) -> list[Post]:
    """
    连接Bluesky firehose，按关键词过滤，采集指定时长。

    Args:
        query: 关键词，逗号分隔多个 (e.g. "iran,war,missile")
        duration_seconds: 监听多少秒
        max_posts: 最多采集多少条

    Returns:
        List[Post] — 匹配的帖子
    """
    keywords = [kw.strip().lower() for kw in query.split(",")]
    posts = []
    import time
    start = time.time()

    print(f"[BLUESKY] Listening for {duration_seconds}s, keywords: {keywords}")

    try:
        async with websockets.connect(JETSTREAM_URL) as ws:
            while time.time() - start < duration_seconds and len(posts) < max_posts:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=2)
                    event = json.loads(message)

                    if event.get("kind") != "commit":
                        continue
                    commit = event.get("commit", {})
                    if commit.get("operation") != "create":
                        continue
                    if commit.get("collection") != "app.bsky.feed.post":
                        continue

                    record = commit.get("record", {})
                    text = record.get("text", "")

                    if not any(kw in text.lower() for kw in keywords):
                        continue

                    did = event.get("did", "unknown")
                    post_id = f"bsky_{did[:12]}_{commit.get('rkey', '')[:8]}"

                    posts.append(Post(
                        id=post_id,
                        source="bluesky",
                        author=did,
                        text=text,
                        timestamp=record.get("createdAt", datetime.now(timezone.utc).isoformat()),
                    ))

                    print(f"  [BSKY] {text[:80]}...")

                except asyncio.TimeoutError:
                    continue

    except Exception as e:
        print(f"[BLUESKY] Error: {e}")

    print(f"[BLUESKY] {len(posts)} posts collected")
    return posts


if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "iran"
    results = asyncio.run(fetch(query, duration_seconds=10))
    for p in results[:5]:
        print(f"  [{p.author[:15]}] {p.text[:100]}")
