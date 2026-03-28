"""
Google News RSS — 最快最稳的新闻源
完全免费，无需key，直接HTTP GET
50+主流媒体实时文章（CNN, WSJ, BBC, Reuters, AP...）
"""
import asyncio
import hashlib
import xml.etree.ElementTree as ET
import httpx
from models import Post


async def fetch(query: str, max_results: int = 50) -> list[Post]:
    """
    从Google News RSS拉取匹配关键词的最新文章。

    Args:
        query: 搜索关键词 (e.g. "iran war")
        max_results: 最多返回条数

    Returns:
        List[Post] — 统一格式的文章列表
    """
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    posts = []

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        if resp.status_code != 200:
            print(f"[GOOGLE NEWS] HTTP {resp.status_code}")
            return posts

        root = ET.fromstring(resp.text)

        for item in root.findall(".//item")[:max_results]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            source_elem = item.find("source")
            source_name = source_elem.text if source_elem is not None else "Unknown"

            post_id = f"gnews_{hashlib.md5(link.encode()).hexdigest()[:12]}"

            posts.append(Post(
                id=post_id,
                source="google_news",
                author=source_name,
                text=title,
                timestamp=pub_date,
                url=link,
            ))

    print(f"[GOOGLE NEWS] {len(posts)} articles collected")
    return posts


if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "iran war"
    results = asyncio.run(fetch(query))
    for p in results[:5]:
        print(f"  [{p.author}] {p.text}")
