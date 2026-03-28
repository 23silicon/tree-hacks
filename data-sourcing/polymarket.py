"""
Polymarket Gamma API — 预测市场数据
完全免费，无需认证
拉取与话题相关的活跃预测市场及其价格
"""
import asyncio
import json
from datetime import datetime, timezone
import httpx
from models import MarketData

GAMMA_API = "https://gamma-api.polymarket.com"


async def fetch(query: str) -> list[MarketData]:
    """
    搜索Polymarket上与关键词匹配的活跃市场。

    Args:
        query: 搜索关键词 (e.g. "iran")

    Returns:
        List[MarketData] — 匹配的市场数据
    """
    markets = []
    query_lower = query.lower()

    async with httpx.AsyncClient() as client:
        # 搜索 markets endpoint
        resp = await client.get(
            f"{GAMMA_API}/markets",
            params={"limit": 50, "active": True, "closed": False},
            timeout=10
        )
        if resp.status_code == 200:
            for m in resp.json():
                if query_lower in m.get("question", "").lower():
                    markets.append(_parse_market(m))

        # 搜索 events endpoint
        resp2 = await client.get(
            f"{GAMMA_API}/events",
            params={"limit": 30, "active": True, "closed": False},
            timeout=10
        )
        if resp2.status_code == 200:
            for event in resp2.json():
                title = event.get("title", "").lower()
                if query_lower in title:
                    for m in event.get("markets", []):
                        mid = m.get("id", "")
                        if mid not in [x.id for x in markets]:
                            markets.append(_parse_market(m))

    print(f"[POLYMARKET] {len(markets)} matching markets found")
    return markets


def _parse_market(m: dict) -> MarketData:
    """Parse raw market JSON into MarketData."""
    prices_str = m.get("outcomePrices", "[]")
    prices = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
    yes = float(prices[0]) if len(prices) > 0 else 0
    no = float(prices[1]) if len(prices) > 1 else 0

    return MarketData(
        id=m.get("id", ""),
        question=m.get("question", ""),
        yes_price=yes,
        no_price=no,
        volume=float(m.get("volumeNum", 0) or 0),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "iran"
    results = asyncio.run(fetch(query))
    for m in results[:5]:
        print(f"  [{m.yes_price:.1%} YES] {m.question[:70]}  (Vol: ${m.volume:,.0f})")
