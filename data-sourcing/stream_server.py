"""
HIVEMIND DATA STREAM
Fast data vacuum → WebSocket push to teammates

Start:
    python stream_server.py "iran war"

Teammates connect:
    ws://YOUR_IP:8765

Every message is one JSON object with "type" and "source" fields.
"""
import asyncio
import json
import time
import sys
import hashlib
import xml.etree.ElementTree as ET

import httpx
import websockets
from websockets.asyncio.server import serve

# ============================================================
# CONNECTIONS
# ============================================================

CONNECTIONS: set = set()
ALL_DATA: list[dict] = []
SEEN_IDS: set = set()


async def broadcast(data: dict):
    global CONNECTIONS
    if data.get("id") in SEEN_IDS:
        return
    if data.get("id"):
        SEEN_IDS.add(data["id"])
    ALL_DATA.append(data)
    msg = json.dumps(data, ensure_ascii=False)
    dead = set()
    for ws in CONNECTIONS:
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    CONNECTIONS -= dead


# ============================================================
# SOURCE: Google News RSS (多角度并行查询)
# ============================================================

async def fetch_google_news(query: str, region: str = "US:en") -> int:
    """单个Google News RSS查询"""
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid={region}"
    count = 0
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=10)
            if resp.status_code != 200:
                return 0
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                source_el = item.find("source")
                source_name = source_el.text if source_el is not None else "Unknown"
                pid = f"gnews_{hashlib.md5(link.encode()).hexdigest()[:12]}"

                await broadcast({
                    "type": "news",
                    "id": pid,
                    "source": "google_news",
                    "author": source_name,
                    "text": title,
                    "timestamp": pub_date,
                    "url": link,
                    "query": query,
                })
                count += 1
        except Exception as e:
            print(f"  [GNEWS] Error on '{query}': {e}")
    return count


async def scrape_all_news(topic: str):
    """多角度并行查询Google News — 最大化覆盖"""
    # 从主题派生多个搜索角度
    base_words = topic.split()
    queries = [
        topic,                                    # 原始查询
        f"{topic} timeline",                      # 时间线
        f"{topic} latest",                        # 最新
        f"{topic} breaking",                      # 突发
        f"{topic} analysis",                      # 分析
        f"{topic} reaction",                      # 反应
        f"{topic} economic impact",               # 经济影响
        f"{topic} diplomatic",                    # 外交
    ]
    # 只取前6个避免太多请求
    queries = queries[:6]

    print(f"[GOOGLE NEWS] Launching {len(queries)} parallel queries...")
    results = await asyncio.gather(*[fetch_google_news(q) for q in queries])
    total = sum(results)
    print(f"[GOOGLE NEWS] Done — {total} articles (deduped: {len([d for d in ALL_DATA if d.get('source') == 'google_news'])})")


# ============================================================
# SOURCE: Major news RSS feeds (直接拉主流媒体)
# ============================================================

RSS_FEEDS = {
    "Reuters World": "https://feeds.reuters.com/Reuters/worldNews",
    "AP News": "https://rsshub.app/apnews/topics/world-news",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "NPR News": "https://feeds.npr.org/1001/rss.xml",
}


async def fetch_rss(name: str, url: str, topic: str) -> int:
    """拉一个RSS feed，过滤匹配topic的文章"""
    keywords = [kw.lower() for kw in topic.split()]
    count = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            resp = await client.get(url, timeout=10)
            if resp.status_code != 200:
                return 0
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                desc = item.findtext("description", "")
                combined = f"{title} {desc}".lower()

                if not any(kw in combined for kw in keywords):
                    continue

                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                pid = f"rss_{hashlib.md5(link.encode()).hexdigest()[:12]}"

                await broadcast({
                    "type": "news",
                    "id": pid,
                    "source": name,
                    "author": name,
                    "text": title,
                    "description": desc[:300] if desc else "",
                    "timestamp": pub_date,
                    "url": link,
                })
                count += 1
        except Exception as e:
            print(f"  [RSS:{name}] Error: {e}")
    return count


async def scrape_all_rss(topic: str):
    """并行拉所有RSS feeds"""
    print(f"[RSS FEEDS] Fetching {len(RSS_FEEDS)} feeds...")
    results = await asyncio.gather(*[
        fetch_rss(name, url, topic)
        for name, url in RSS_FEEDS.items()
    ])
    for (name, _), count in zip(RSS_FEEDS.items(), results):
        if count > 0:
            print(f"  [RSS:{name}] {count} matching articles")
    print(f"[RSS FEEDS] Done — {sum(results)} total articles")


# ============================================================
# SOURCE: Bluesky firehose (实时流)
# ============================================================

async def stream_bluesky(topic: str, duration: int = 20):
    """持续监听Bluesky firehose"""
    keywords = [kw.strip().lower() for kw in topic.split()]
    start = time.time()
    count = 0

    print(f"[BLUESKY] Listening for {duration}s, keywords: {keywords}")
    try:
        async with websockets.connect(
            "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"
        ) as ws:
            while time.time() - start < duration:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2)
                    event = json.loads(raw)

                    if event.get("kind") != "commit":
                        continue
                    commit = event.get("commit", {})
                    if commit.get("operation") != "create" or commit.get("collection") != "app.bsky.feed.post":
                        continue

                    text = commit.get("record", {}).get("text", "")
                    if not any(kw in text.lower() for kw in keywords):
                        continue

                    did = event.get("did", "unknown")
                    pid = f"bsky_{did[:12]}_{commit.get('rkey', '')[:8]}"

                    await broadcast({
                        "type": "social",
                        "id": pid,
                        "source": "bluesky",
                        "author": did,
                        "text": text,
                        "timestamp": commit.get("record", {}).get("createdAt", ""),
                    })
                    count += 1
                    print(f"  [BSKY] {text[:80]}")

                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        print(f"[BLUESKY] Error: {e}")

    print(f"[BLUESKY] {count} posts captured")


# ============================================================
# SOURCE: Polymarket (预测市场)
# ============================================================

async def scrape_polymarket(query: str):
    """拉Polymarket匹配的市场"""
    query_lower = query.lower()
    count = 0

    async with httpx.AsyncClient() as client:
        for endpoint in ["/markets", "/events"]:
            try:
                resp = await client.get(
                    f"https://gamma-api.polymarket.com{endpoint}",
                    params={"limit": 50, "active": True, "closed": False},
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue

                items = resp.json()
                for item in items:
                    # markets endpoint
                    if "question" in item:
                        if query_lower not in item.get("question", "").lower():
                            continue
                        prices = item.get("outcomePrices", "[]")
                        if isinstance(prices, str):
                            prices = json.loads(prices)
                        await broadcast({
                            "type": "market",
                            "id": item.get("id", ""),
                            "source": "polymarket",
                            "question": item.get("question", ""),
                            "yes_price": float(prices[0]) if len(prices) > 0 else 0,
                            "no_price": float(prices[1]) if len(prices) > 1 else 0,
                            "volume": float(item.get("volumeNum", 0) or 0),
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        })
                        count += 1

                    # events endpoint
                    elif "markets" in item:
                        if query_lower not in item.get("title", "").lower():
                            continue
                        for m in item.get("markets", []):
                            prices = m.get("outcomePrices", "[]")
                            if isinstance(prices, str):
                                prices = json.loads(prices)
                            mid = m.get("id", "")
                            if mid not in SEEN_IDS:
                                await broadcast({
                                    "type": "market",
                                    "id": mid,
                                    "source": "polymarket",
                                    "question": m.get("question", ""),
                                    "yes_price": float(prices[0]) if len(prices) > 0 else 0,
                                    "no_price": float(prices[1]) if len(prices) > 1 else 0,
                                    "volume": float(m.get("volumeNum", 0) or 0),
                                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                })
                                count += 1
            except Exception as e:
                print(f"  [POLYMARKET] Error: {e}")

    print(f"[POLYMARKET] {count} markets found")


# ============================================================
# POLLING LOOP (持续刷新)
# ============================================================

async def poll_loop(topic: str, interval: int = 45):
    """持续拉新数据"""
    while True:
        await asyncio.sleep(interval)
        print(f"\n[REFRESH] Pulling new data...")
        await asyncio.gather(
            scrape_all_news(topic),
            scrape_all_rss(topic),
            scrape_polymarket(topic),
        )
        print(f"[REFRESH] Total items streamed: {len(ALL_DATA)}")


async def bluesky_loop(topic: str):
    """持续监听Bluesky"""
    while True:
        await stream_bluesky(topic, duration=30)
        await asyncio.sleep(3)


# ============================================================
# WS HANDLER + MAIN
# ============================================================

async def ws_handler(ws):
    CONNECTIONS.add(ws)
    addr = ws.remote_address
    print(f"[WS] +1 client ({addr}) — {len(CONNECTIONS)} connected")

    # 发送快照
    if ALL_DATA:
        await ws.send(json.dumps({
            "type": "snapshot",
            "data": ALL_DATA,
            "count": len(ALL_DATA),
        }, ensure_ascii=False))

    try:
        async for msg in ws:
            pass  # 前端不需要发消息过来，纯推流
    except websockets.ConnectionClosed:
        pass
    finally:
        CONNECTIONS.discard(ws)
        print(f"[WS] -1 client — {len(CONNECTIONS)} connected")


async def main(topic: str, port: int = 8765):
    # 获取本机IP
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"

    print(f"""
{'='*60}
  HIVEMIND DATA STREAM
  Topic: {topic}
{'='*60}

  Tell your teammates to connect to:

    ws://{local_ip}:{port}

  They will receive JSON messages with types:
    "news"    — news articles
    "social"  — social media posts
    "market"  — prediction market data
    "snapshot"— full data dump (on connect)

{'='*60}
""")

    async with serve(ws_handler, "0.0.0.0", port):
        # 初始采集（全部并行）
        print("[INIT] Starting initial data collection...\n")
        await asyncio.gather(
            scrape_all_news(topic),
            scrape_all_rss(topic),
            scrape_polymarket(topic),
            stream_bluesky(topic, duration=15),
        )

        print(f"\n[INIT] Done — {len(ALL_DATA)} total items streamed")
        print(f"[INIT] Entering continuous mode (refresh every 45s + live Bluesky)\n")

        # 持续运行
        await asyncio.gather(
            poll_loop(topic, interval=45),
            bluesky_loop(topic),
        )


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "iran war"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    try:
        asyncio.run(main(topic, port))
    except KeyboardInterrupt:
        print("\n[SERVER] Stopped.")
