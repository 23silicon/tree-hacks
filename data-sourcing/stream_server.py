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
import os
import hashlib
import xml.etree.ElementTree as ET

import httpx
import websockets
from websockets.asyncio.server import serve
from dotenv import load_dotenv
from aggregator import aggregator_loop
from enrichment import enrichment_loop, enrich_data

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# ============================================================
# CONNECTIONS
# ============================================================

CONNECTIONS: set = set()
ALL_DATA: list[dict] = []
SEEN_IDS: set = set()
LATEST_TOPICS: list[dict] = []  # 最新发现的话题，新客户端连上立刻发


async def broadcast(data: dict):
    global CONNECTIONS, LATEST_TOPICS
    if data.get("id") in SEEN_IDS:
        return
    if data.get("id"):
        SEEN_IDS.add(data["id"])
    if data.get("type") == "topics":
        LATEST_TOPICS = data.get("topics", [])
    elif data.get("type") == "enrichment":
        LATEST_ENRICHMENT.update(data)
    elif data.get("type") not in ("status",):
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


async def _fetch_gnews_url(url: str, query: str) -> int:
    """Fetch a specific Google News RSS URL."""
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
                    "type": "news", "id": pid, "source": "google_news",
                    "author": source_name, "text": title,
                    "timestamp": pub_date, "url": link, "query": query,
                })
                count += 1
        except Exception as e:
            pass
    return count


async def scrape_all_news(topic: str):
    """多角度 + 多地区并行查询Google News"""
    queries = [
        topic,
        f"{topic} latest",
        f"{topic} breaking",
        f"{topic} analysis",
        f"{topic} reaction",
        f"{topic} economic impact",
        f"{topic} timeline",
        f"{topic} opinion",
        f"{topic} update today",
    ]

    # 多地区：同一话题在不同国家的报道
    REGIONS = [
        ("US:en", "en-US", "US"),
        ("GB:en", "en-GB", "GB"),
        ("AU:en", "en-AU", "AU"),
        ("IN:en", "en-IN", "IN"),
        ("CA:en", "en-CA", "CA"),
    ]

    all_tasks = []
    for q in queries[:6]:
        all_tasks.append(fetch_google_news(q))  # default US
    # 主查询的多地区版本
    for ceid, hl, gl in REGIONS[1:]:  # skip US (already have it)
        url = f"https://news.google.com/rss/search?q={topic}&hl={hl}&gl={gl}&ceid={ceid}"
        all_tasks.append(_fetch_gnews_url(url, topic))

    print(f"[GOOGLE NEWS] Launching {len(all_tasks)} parallel queries (6 angles + 4 regions)...")
    results = await asyncio.gather(*all_tasks)
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
    "WSJ World": "https://feeds.content.dowjones.io/public/rss/RSSWorldNews.xml",
    "WSJ Opinion": "https://feeds.content.dowjones.io/public/rss/RSSOpinion.xml",
    "Fox News World": "https://moxie.foxnews.com/google-publisher/world.xml",
    "Fox News Politics": "https://moxie.foxnews.com/google-publisher/politics.xml",
    "CBS News": "https://www.cbsnews.com/latest/rss/world",
    "ABC News": "https://abcnews.go.com/abcnews/internationalheadlines",
    "The Hill": "https://thehill.com/feed/",
    "NY Post": "https://nypost.com/feed/",
    "Guardian World": "https://www.theguardian.com/world/rss",
    "CNN Top": "http://rss.cnn.com/rss/edition.rss",
    "NBC News": "https://feeds.nbcnews.com/nbcnews/public/news",
    "Politico": "https://rss.politico.com/politics-news.xml",
    "Axios": "https://api.axios.com/feed/",
    "Business Insider": "https://www.businessinsider.com/rss",
    "Yahoo News": "https://news.yahoo.com/rss/",
    "Drudge Report": "https://feeds.feedburner.com/DrudgeReportFeed",
    "MarketWatch": "http://feeds.marketwatch.com/marketwatch/topstories/",
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
# SOURCE: Reddit (公开JSON API，无需认证)
# ============================================================

REDDIT_SUBREDDITS = [
    "worldnews",
    "news",
    "geopolitics",
    "politics",
    "economics",
    "foreignpolicy",
    "MiddleEastNews",
    "iran",
    "military",
    "IntelligenceNews",
    "worldpolitics",
    "anime_titties",        # actually a serious world news sub
    "neutralnews",
    "UpliftingNews",
    "business",
    "stocks",
    "wallstreetbets",
]

REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}


async def reddit_get(client: httpx.AsyncClient, url: str, params: dict) -> dict | None:
    """Reddit GET with retry on 429."""
    for attempt in range(3):
        try:
            resp = await client.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"  [REDDIT] Rate limited, waiting {wait}s...")
                await asyncio.sleep(wait)
                continue
            return None
        except Exception as e:
            print(f"  [REDDIT] Request error: {e}")
            return None
    return None


async def scrape_reddit(query: str):
    """搜索Reddit帖子 — 通过Google News RSS抓Reddit内容绕过限流"""
    count = 0

    # 方法1: Google News搜reddit站内内容（不受Reddit限流）
    reddit_news_url = f"https://news.google.com/rss/search?q={query}+site:reddit.com&hl=en-US&gl=US&ceid=US:en"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            resp = await client.get(reddit_news_url, timeout=10)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item in root.findall(".//item"):
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    pub_date = item.findtext("pubDate", "")
                    pid = f"reddit_g_{hashlib.md5(link.encode()).hexdigest()[:12]}"

                    await broadcast({
                        "type": "social",
                        "id": pid,
                        "source": "reddit",
                        "author": "Reddit (via Google)",
                        "text": title,
                        "timestamp": pub_date,
                        "url": link,
                    })
                    count += 1
        except Exception as e:
            print(f"  [REDDIT:google] Error: {e}")

    # 方法2: 直接Reddit JSON（带重试，可能被限流）
    async with httpx.AsyncClient(follow_redirects=True, headers=REDDIT_HEADERS) as client:
        try:
            result = await reddit_get(client, "https://www.reddit.com/search.json",
                {"q": query, "sort": "new", "limit": 100, "t": "day"})
            if result:
                data = result.get("data", {}).get("children", [])
                for item in data:
                    d = item.get("data", {})
                    pid = f"reddit_{d.get('id', '')}"
                    title = d.get("title", "")
                    selftext = d.get("selftext", "")[:200]
                    text = f"{title}. {selftext}" if selftext else title

                    await broadcast({
                        "type": "social",
                        "id": pid,
                        "source": "reddit",
                        "author": f"r/{d.get('subreddit', '?')} u/{d.get('author', '?')}",
                        "text": text,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(d.get("created_utc", 0))),
                        "url": f"https://reddit.com{d.get('permalink', '')}",
                        "score": d.get("score", 0),
                        "comments": d.get("num_comments", 0),
                    })
                    count += 1
        except Exception as e:
            print(f"  [REDDIT] Search error: {e}")

        # 2. 每个子版块：关键词搜索 + 热门帖子（不限关键词）
        for sub in REDDIT_SUBREDDITS:
            try:
                # 搜索匹配的
                result = await reddit_get(client, f"https://www.reddit.com/r/{sub}/search.json",
                    {"q": query, "sort": "new", "restrict_sr": "on", "limit": 50, "t": "day"})
                if result:
                    data = result.get("data", {}).get("children", [])
                    for item in data:
                        d = item.get("data", {})
                        pid = f"reddit_{d.get('id', '')}"
                        title = d.get("title", "")
                        selftext = d.get("selftext", "")[:200]
                        text = f"{title}. {selftext}" if selftext else title

                        await broadcast({
                            "type": "social",
                            "id": pid,
                            "source": "reddit",
                            "author": f"r/{sub} u/{d.get('author', '?')}",
                            "text": text,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(d.get("created_utc", 0))),
                            "url": f"https://reddit.com{d.get('permalink', '')}",
                            "score": d.get("score", 0),
                            "comments": d.get("num_comments", 0),
                        })
                        count += 1
                await asyncio.sleep(1)

                await asyncio.sleep(2)
                # 也拉这个版块的最新帖子（不限关键词，拉更多数据）
                result2 = await reddit_get(client, f"https://www.reddit.com/r/{sub}/new.json",
                    {"limit": 50})
                if result2:
                    data = result2.get("data", {}).get("children", [])
                    for item in data:
                        d = item.get("data", {})
                        pid = f"reddit_{d.get('id', '')}"
                        title = d.get("title", "")
                        selftext = d.get("selftext", "")[:200]
                        text = f"{title}. {selftext}" if selftext else title

                        await broadcast({
                            "type": "social",
                            "id": pid,
                            "source": "reddit",
                            "author": f"r/{sub} u/{d.get('author', '?')}",
                            "text": text,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(d.get("created_utc", 0))),
                            "url": f"https://reddit.com{d.get('permalink', '')}",
                            "score": d.get("score", 0),
                            "comments": d.get("num_comments", 0),
                        })
                        count += 1
                await asyncio.sleep(1)
            except Exception as e:
                print(f"  [REDDIT:r/{sub}] Error: {e}")

    print(f"[REDDIT] {count} posts collected")


async def scrape_reddit_comments(query: str):
    """抓Reddit热门帖子的评论 — 这是大量数据的来源"""
    keywords = [kw.lower() for kw in query.split()]
    count = 0

    async with httpx.AsyncClient(follow_redirects=True, headers=REDDIT_HEADERS) as client:
        # 先找热门帖子
        try:
            resp = await client.get(
                "https://www.reddit.com/search.json",
                params={"q": query, "sort": "hot", "limit": 10, "t": "day"},
                timeout=10,
            )
            if resp.status_code != 200:
                return

            posts = resp.json().get("data", {}).get("children", [])

            for post in posts[:8]:
                permalink = post.get("data", {}).get("permalink", "")
                if not permalink:
                    continue

                await asyncio.sleep(1)  # rate limit

                # 抓这个帖子的评论
                try:
                    resp2 = await client.get(
                        f"https://www.reddit.com{permalink}.json",
                        params={"limit": 50, "sort": "top"},
                        timeout=10,
                    )
                    if resp2.status_code != 200:
                        continue

                    data = resp2.json()
                    if len(data) < 2:
                        continue

                    comments = data[1].get("data", {}).get("children", [])
                    for comment in comments:
                        c = comment.get("data", {})
                        body = c.get("body", "")
                        if not body or body == "[deleted]" or body == "[removed]":
                            continue

                        cid = f"reddit_c_{c.get('id', '')}"

                        await broadcast({
                            "type": "social",
                            "id": cid,
                            "source": "reddit",
                            "author": f"r/{c.get('subreddit', '?')} u/{c.get('author', '?')}",
                            "text": body[:500],
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(c.get("created_utc", 0))),
                            "url": f"https://reddit.com{permalink}",
                            "score": c.get("score", 0),
                        })
                        count += 1

                except Exception as e:
                    print(f"  [REDDIT:comments] Error: {e}")

        except Exception as e:
            print(f"  [REDDIT:comments] Error: {e}")

    print(f"[REDDIT COMMENTS] {count} comments collected")


async def reddit_loop(topic: str):
    """持续轮询Reddit，每60秒一次（避免429限流）"""
    while True:
        await asyncio.sleep(60)
        await scrape_reddit(topic)
        await asyncio.sleep(10)
        await scrape_reddit_comments(topic)


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
# SOURCE: Google Trends (热搜话题自动发现)
# ============================================================

async def fetch_google_trends() -> list[str]:
    """拉Google Trends热搜词，返回当前最热的话题列表"""
    trending = []
    async with httpx.AsyncClient() as client:
        # Google Trends RSS — 实时热搜
        try:
            resp = await client.get(
                "https://trends.google.com/trending/rss?geo=US",
                timeout=10,
            )
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                    title = item.findtext("{http://www.w3.org/2005/Atom}title", "")
                    if title:
                        trending.append(title)

                # fallback: try standard RSS item format
                if not trending:
                    for item in root.findall(".//item"):
                        title = item.findtext("title", "")
                        if title:
                            trending.append(title)
        except Exception as e:
            print(f"  [TRENDS] RSS error: {e}")

        # Backup: Google Trends daily trends page
        if not trending:
            try:
                resp = await client.get(
                    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US",
                    timeout=10,
                )
                if resp.status_code == 200:
                    root = ET.fromstring(resp.text)
                    for item in root.findall(".//item"):
                        title = item.findtext("title", "")
                        if title:
                            trending.append(title)
            except Exception:
                pass

    if trending:
        print(f"[TRENDS] Found {len(trending)} trending topics: {', '.join(trending[:5])}")
    else:
        print(f"[TRENDS] Could not fetch trending topics")

    return trending[:20]


async def scrape_trending():
    """自动发现Google Trends热搜 → 对每个热门话题采集新闻"""
    trending = await fetch_google_trends()

    for topic in trending[:5]:  # 只取top 5避免太多请求
        await broadcast({"type": "status", "message": f"Scraping trending: {topic}"})
        await scrape_all_news(topic)
        await asyncio.sleep(1)

    if trending:
        await broadcast({
            "type": "trending",
            "topics": trending,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })


# ============================================================
# SOURCE: Hacker News (免费API，科技/商业话题)
# ============================================================

async def scrape_hackernews():
    """拉Hacker News前30条热门帖子"""
    count = 0
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10)
            if resp.status_code != 200:
                return

            story_ids = resp.json()[:30]

            # 并行拉每个story的详情
            async def fetch_story(sid):
                nonlocal count
                try:
                    r = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5)
                    if r.status_code != 200:
                        return
                    s = r.json()
                    if not s or s.get("type") != "story":
                        return
                    await broadcast({
                        "type": "news",
                        "id": f"hn_{sid}",
                        "source": "hackernews",
                        "author": s.get("by", "?"),
                        "text": s.get("title", ""),
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(s.get("time", 0))),
                        "url": s.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                        "score": s.get("score", 0),
                        "comments": s.get("descendants", 0),
                    })
                    count += 1
                except Exception:
                    pass

            await asyncio.gather(*[fetch_story(sid) for sid in story_ids])
        except Exception as e:
            print(f"  [HN] Error: {e}")

    print(f"[HACKER NEWS] {count} stories collected")


# ============================================================
# SOURCE: YouTube Data API (视频搜索 + 评论抓取)
# ============================================================

async def scrape_youtube(query: str):
    """搜索YouTube视频 + 抓热门评论"""
    if not YOUTUBE_API_KEY:
        print("[YOUTUBE] No API key, skipping")
        return

    count = 0
    async with httpx.AsyncClient() as client:
        # 1. 搜索相关视频
        try:
            resp = await client.get("https://www.googleapis.com/youtube/v3/search", params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "date",
                "maxResults": 20,
                "key": YOUTUBE_API_KEY,
            }, timeout=10)

            if resp.status_code != 200:
                print(f"[YOUTUBE] Search error: {resp.status_code}")
                return

            videos = resp.json().get("items", [])
            video_ids = []

            for v in videos:
                vid = v.get("id", {}).get("videoId", "")
                snippet = v.get("snippet", {})
                title = snippet.get("title", "")
                channel = snippet.get("channelTitle", "")
                published = snippet.get("publishedAt", "")
                description = snippet.get("description", "")[:200]

                pid = f"yt_{vid}"
                video_ids.append(vid)

                await broadcast({
                    "type": "social",
                    "id": pid,
                    "source": "youtube",
                    "author": channel,
                    "text": f"{title}. {description}" if description else title,
                    "timestamp": published,
                    "url": f"https://youtube.com/watch?v={vid}",
                })
                count += 1

        except Exception as e:
            print(f"[YOUTUBE] Search error: {e}")
            return

        # 2. 抓前5个视频的评论
        for vid in video_ids[:5]:
            try:
                resp = await client.get("https://www.googleapis.com/youtube/v3/commentThreads", params={
                    "part": "snippet",
                    "videoId": vid,
                    "order": "relevance",
                    "maxResults": 20,
                    "key": YOUTUBE_API_KEY,
                }, timeout=10)

                if resp.status_code != 200:
                    continue

                comments = resp.json().get("items", [])
                for c in comments:
                    cs = c.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                    text = cs.get("textDisplay", "")
                    author = cs.get("authorDisplayName", "")
                    published = cs.get("publishedAt", "")
                    likes = cs.get("likeCount", 0)
                    cid = f"yt_c_{c.get('id', '')[:12]}"

                    await broadcast({
                        "type": "social",
                        "id": cid,
                        "source": "youtube",
                        "author": f"YT Comment: {author}",
                        "text": text[:500],
                        "timestamp": published,
                        "url": f"https://youtube.com/watch?v={vid}",
                        "score": likes,
                    })
                    count += 1

            except Exception as e:
                continue

    print(f"[YOUTUBE] {count} videos + comments collected")


# ============================================================
# ON-DEMAND TOPIC SCRAPE (用户输入话题 → 立刻采集)
# ============================================================

async def on_demand_scrape(topic: str):
    """用户输入一个新话题，立刻并行采集 → 单独聚合 → sentiment分析 → 推送"""
    await broadcast({"type": "status", "message": f"Searching for: {topic}..."})
    print(f"\n[ON-DEMAND] Scraping topic: {topic}")

    before = len(ALL_DATA)

    await asyncio.gather(
        scrape_all_news(topic),
        scrape_all_rss(topic),
        scrape_polymarket(topic),
        scrape_reddit(topic),
        scrape_youtube(topic),
    )

    new_count = len(ALL_DATA) - before
    new_items = ALL_DATA[before:]  # 只取这次新采集的数据
    print(f"[ON-DEMAND] Done — {new_count} new items for '{topic}'")
    await broadcast({"type": "status", "message": f"Found {new_count} items for: {topic}. Analyzing..."})

    # 只对新数据做聚合+sentiment
    from aggregator import analyze_topic_with_sentiment, HAS_ANTHROPIC
    if HAS_ANTHROPIC and new_items:
        result = await analyze_topic_with_sentiment(topic, new_items)
        if result:
            await broadcast(result)
            save_json()
            # 也保存这个话题的单独JSON
            topic_path = os.path.join(OUTPUT_DIR, f"topic_{topic.replace(' ', '_')}.json")
            with open(topic_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"[ON-DEMAND] Saved {topic_path}")
    else:
        # fallback: 只推数据不做sentiment
        from aggregator import discover_topics_keyword
        topics = discover_topics_keyword(new_items)
        if topics:
            await broadcast({
                "type": "topics",
                "topics": topics,
                "mode": "keyword",
                "data_count": len(ALL_DATA),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })


# ============================================================
# JSON OUTPUT (队友可以直接读)
# ============================================================

OUTPUT_DIR = os.path.dirname(__file__)

def save_json(topics_data=None):
    """保存当前所有数据到JSON文件"""
    output = {
        "meta": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_items": len(ALL_DATA),
            "sources": {},
        },
        "topics": topics_data or LATEST_TOPICS,
        "items": ALL_DATA[-500:],  # 最近500条
    }
    # 统计来源
    for item in ALL_DATA:
        s = item.get("source", "unknown")
        output["meta"]["sources"][s] = output["meta"]["sources"].get(s, 0) + 1

    path = os.path.join(OUTPUT_DIR, "hivemind_output.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


LATEST_ENRICHMENT: dict = {}  # 最新的enrichment结果


async def json_save_loop(interval: int = 30):
    """每30秒保存统一输出JSON — 队友只需要读这一个文件"""
    while True:
        await asyncio.sleep(interval)
        if not ALL_DATA:
            continue

        save_json()

        # 统一输出: 合并所有分析结果到一个文件
        unified = {
            "meta": {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total_raw_items": len(ALL_DATA),
                "sources": {},
            },
            # 话题发现
            "topics": LATEST_TOPICS,
            # Enrichment (去重+事件+实体+矛盾)
            "enrichment": LATEST_ENRICHMENT if LATEST_ENRICHMENT else None,
            # 最近的原始数据 (去重前)
            "raw_items": [
                {k: v for k, v in item.items() if k not in ("raw",)}
                for item in ALL_DATA[-200:]
            ],
        }

        for item in ALL_DATA:
            s = item.get("source", "unknown")
            unified["meta"]["sources"][s] = unified["meta"]["sources"].get(s, 0) + 1

        path = os.path.join(OUTPUT_DIR, "final_output.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(unified, f, indent=2, ensure_ascii=False)

        print(f"[JSON] Saved final_output.json ({len(ALL_DATA)} items, {len(LATEST_TOPICS)} topics)")


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
            scrape_reddit(topic),
            scrape_hackernews(),
            scrape_trending(),
            scrape_youtube(topic),
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

    # 发送快照（限制大小，只发最近200条）
    if ALL_DATA:
        snapshot_items = ALL_DATA[-200:]
        await ws.send(json.dumps({
            "type": "snapshot",
            "data": snapshot_items,
            "count": len(ALL_DATA),
            "total": len(ALL_DATA),
        }, ensure_ascii=False))

    # 立刻发送最新topics
    if LATEST_TOPICS:
        await ws.send(json.dumps({
            "type": "topics",
            "topics": LATEST_TOPICS,
            "data_count": len(ALL_DATA),
        }, ensure_ascii=False))

    # 立刻发送最新enrichment
    if LATEST_ENRICHMENT:
        await ws.send(json.dumps(LATEST_ENRICHMENT, ensure_ascii=False))

    try:
        async for msg in ws:
            # 前端可以发请求
            try:
                cmd = json.loads(msg)
                if cmd.get("action") == "search_topic":
                    # 用户输入新话题 → 重新采集
                    new_topic = cmd.get("topic", "")
                    if new_topic:
                        print(f"[WS] Client requested topic: {new_topic}")
                        asyncio.create_task(on_demand_scrape(new_topic))
            except json.JSONDecodeError:
                pass
    except websockets.ConnectionClosed:
        pass
    finally:
        CONNECTIONS.discard(ws)
        print(f"[WS] -1 client — {len(CONNECTIONS)} connected")


def run_http_server(http_port: int):
    """Serve live_viewer.html on an HTTP port so the browser can connect to WS."""
    from http.server import HTTPServer, SimpleHTTPRequestHandler
    import threading

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=os.path.dirname(__file__), **kwargs)
        def log_message(self, format, *args):
            pass  # suppress logs

    server = HTTPServer(("0.0.0.0", http_port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[HTTP] Serving viewer at http://0.0.0.0:{http_port}/live_viewer.html")


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

    http_port = port + 1  # 8766
    run_http_server(http_port)

    print(f"""
{'='*60}
  HIVEMIND DATA STREAM
  Default topic: {topic} (also scrapes Google Trends + Hacker News)
{'='*60}

  OPEN IN BROWSER:
    http://{local_ip}:{http_port}/live_viewer.html

  WebSocket for teammates:
    ws://{local_ip}:{port}

{'='*60}
""")

    async with serve(ws_handler, "0.0.0.0", port):
        # 初始采集（全部并行，Bluesky只等5秒不阻塞）
        print("[INIT] Starting initial data collection...\n")
        await asyncio.gather(
            scrape_all_news(topic),
            scrape_all_rss(topic),
            scrape_polymarket(topic),
            scrape_reddit(topic),
            scrape_hackernews(),
            scrape_trending(),
            scrape_youtube(topic),
            stream_bluesky(topic, duration=5),
        )

        print(f"\n[INIT] Done — {len(ALL_DATA)} total items streamed")

        # 立刻跑一次aggregator，不等30秒
        print("[INIT] Running initial topic discovery...\n")
        from aggregator import discover_topics_llm, discover_topics_keyword, HAS_ANTHROPIC
        try:
            if HAS_ANTHROPIC:
                init_topics = await discover_topics_llm(ALL_DATA)
            else:
                init_topics = discover_topics_keyword(ALL_DATA)
            if init_topics:
                await broadcast({
                    "type": "topics",
                    "topics": init_topics,
                    "mode": "llm" if HAS_ANTHROPIC else "keyword",
                    "data_count": len(ALL_DATA),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                })
                # 保存JSON给队友
                save_json(init_topics)
                print(f"[INIT] {len(init_topics)} topics discovered")
        except Exception as e:
            print(f"[INIT] Topic discovery error: {e}")

        # 立刻跑enrichment
        print("[INIT] Running enrichment (dedup + entities + contradictions)...\n")
        try:
            await enrich_data(ALL_DATA, broadcast)
        except Exception as e:
            print(f"[INIT] Enrichment error: {e}")

        print(f"[INIT] Entering continuous mode\n")

        # 持续运行
        await asyncio.gather(
            poll_loop(topic, interval=45),
            reddit_loop(topic),
            bluesky_loop(topic),
            aggregator_loop(ALL_DATA, broadcast, interval=30),
            enrichment_loop(ALL_DATA, broadcast, interval=60),
            json_save_loop(interval=30),
        )


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "iran war"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    try:
        asyncio.run(main(topic, port))
    except KeyboardInterrupt:
        print("\n[SERVER] Stopped.")
