"""
news_fetcher.py — Fetches India financial news from RSS feeds.

Sources:
  - Economic Times (default + markets feed)
  - Moneycontrol

Uses feedparser. Falls back gracefully if feeds are unavailable.
"""

import os
import warnings
from datetime import datetime
from typing import List, Dict, Optional

warnings.filterwarnings("ignore")

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False

from src.mcp_tools.mcp_tools import india_news_mcp, world_news_mcp, NewsItem

# Tavily client — instantiated lazily only if key is present
_tavily_client: Optional["TavilyClient"] = None


def _get_tavily_client() -> Optional["TavilyClient"]:
    """Return a Tavily client if API key is set, else None."""
    global _tavily_client
    if _tavily_client is not None:
        return _tavily_client
    if not TAVILY_AVAILABLE:
        return None
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key or api_key == "tvly-your-key-here":
        return None
    _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


# ─────────────────────────────────────────────────────────────────────────────
# RSS feed definitions
# ─────────────────────────────────────────────────────────────────────────────

INDIA_FEEDS = [
    {
        "url": "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
        "source": "Economic Times",
        "category": "India Business",
        "mcp": "india",
    },
    {
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "source": "ET Markets",
        "category": "Markets",
        "mcp": "india",
    },
    {
        "url": "https://www.business-standard.com/rss/home_page_top_stories.rss",
        "source": "Business Standard",
        "category": "India Business",
        "mcp": "india",
    },
    {
        "url": "https://www.moneycontrol.com/rss/business.xml",
        "source": "Moneycontrol",
        "category": "India Business",
        "mcp": "india",
    },
    {
        "url": "https://www.livemint.com/rss/markets",
        "source": "Livemint",
        "category": "Markets",
        "mcp": "india",
    },
]

# NOTE: Reuters deprecated their free RSS feeds.
# Replaced with CNBC Business (reliable, business-focused).
WORLD_FEEDS = [
    {
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "source": "BBC Business",
        "category": "World Business",
        "mcp": "world",
    },
    {
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "source": "BBC World",
        "category": "Geopolitical",
        "mcp": "world",
    },
    {
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "source": "CNBC Business",
        "category": "World Business",
        "mcp": "world",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Category detection heuristics
# ─────────────────────────────────────────────────────────────────────────────

_RBI_KEYWORDS = ["rbi", "reserve bank", "repo rate", "monetary policy", "inflation", "sebi"]
_EARNINGS_KEYWORDS = ["results", "earnings", "revenue", "profit", "quarterly", "q1", "q2", "q3", "q4", "fy2"]
_FII_KEYWORDS = ["fii", "dii", "foreign", "institutional", "flows", "net buyer", "net seller"]
_GEOPOLITICAL_KEYWORDS = ["war", "conflict", "sanctions", "geopolitical", "tensions", "military", "nato", "opec"]
_COMMODITY_KEYWORDS = ["crude", "oil", "gold", "metals", "brent", "commodity", "opec"]
_FED_KEYWORDS = ["fed", "federal reserve", "powell", "interest rate", "rate hike", "rate cut"]


def _detect_category(title: str, source_category: str) -> str:
    """Auto-detect news category from headline."""
    title_lower = title.lower()
    if any(k in title_lower for k in _RBI_KEYWORDS):
        return "RBI Policy"
    if any(k in title_lower for k in _EARNINGS_KEYWORDS):
        return "Earnings"
    if any(k in title_lower for k in _FII_KEYWORDS):
        return "FII/DII Flows"
    if any(k in title_lower for k in _GEOPOLITICAL_KEYWORDS):
        return "Geopolitical"
    if any(k in title_lower for k in _COMMODITY_KEYWORDS):
        return "Commodity"
    if any(k in title_lower for k in _FED_KEYWORDS):
        return "Fed Policy"
    return source_category


def _india_relevance(title: str, category: str) -> Optional[str]:
    """
    Auto-tag a standard India transmission channel for world news headlines.

    IMPORTANT: These are keyword-matched template strings, NOT LLM-generated analysis.
    They indicate which channel may be relevant — the Geopolitical Agent does the
    actual analysis. Do not treat these as confirmed signals.
    """
    title_lower = title.lower()
    if "fed" in title_lower or "federal reserve" in title_lower:
        return "[auto-tag: rupee channel] Fed policy affects USD/INR and FII equity flows into India."
    if "oil" in title_lower or "crude" in title_lower or "opec" in title_lower:
        return "[auto-tag: oil channel] Crude price directly impacts India CAD, inflation, and RBI rate path."
    if "china" in title_lower:
        return "[auto-tag: EM sentiment channel] China developments affect EM sentiment and India capital flows."
    if "dollar" in title_lower or "usd" in title_lower:
        return "[auto-tag: rupee channel] Dollar strength pressures rupee and can trigger FII outflows."
    if "recession" in title_lower:
        return "[auto-tag: EM sentiment channel] Global recession risk affects IT and export sector earnings."
    if "tariff" in title_lower or "trade war" in title_lower:
        return "[auto-tag: trade channel] Trade policy changes can affect India's IT and pharma export sectors."
    if "israel" in title_lower or "iran" in title_lower or "ukraine" in title_lower or "russia" in title_lower:
        return "[auto-tag: oil/EM channel] Geopolitical conflict may affect crude prices and EM risk appetite."
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Feed fetching
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_feed(feed_config: Dict, max_items: int = 10) -> List[Dict]:
    """Fetch and parse a single RSS feed. Returns list of raw item dicts."""
    if not FEEDPARSER_AVAILABLE:
        return []

    url = feed_config["url"]
    try:
        # Use requests with timeout to avoid hanging
        if REQUESTS_AVAILABLE:
            resp = requests.get(url, timeout=5, headers={"User-Agent": "HMAS/1.0"})
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        else:
            parsed = feedparser.parse(url)

        items = []
        for entry in parsed.entries[:max_items]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            # Parse published date
            published = entry.get("published", entry.get("updated", datetime.now().isoformat()))
            items.append({
                "title": title,
                "source": feed_config["source"],
                "category": _detect_category(title, feed_config["category"]),
                "mcp": feed_config["mcp"],
                "published": published,
            })
        return items

    except Exception as exc:
        print(f"  [WARN] RSS feed unavailable ({feed_config['source']}): {type(exc).__name__}")
        return []


def fetch_tavily_news(
    query: str,
    mcp_tag: str = "india",
    max_results: int = 5,
) -> List[Dict]:
    """
    Search for news via Tavily and return structured items.

    Returns list of item dicts compatible with populate_news_mcps() format.
    Falls back to empty list if Tavily is unavailable or call fails.

    Args:
        query: Search query (e.g., "India stock market today", "RELIANCE Q4 results")
        mcp_tag: "india" or "world" — which MCP to route items to
        max_results: Max articles to return
    """
    client = _get_tavily_client()
    if client is None:
        return []
    try:
        results = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=False,
        )
        items = []
        for r in results.get("results", []):
            title = r.get("title", "").strip()
            if not title:
                continue
            content = r.get("content", title)  # Article snippet — actual content, not just headline
            url = r.get("url", "")
            source = r.get("source") or (url.split("/")[2] if url else "Tavily Search")
            published = r.get("published_date", datetime.now().isoformat())
            items.append({
                "title": title,
                "source": source,
                "content": content,
                "category": _detect_category(title, "India Business" if mcp_tag == "india" else "World Business"),
                "mcp": mcp_tag,
                "published": published,
            })
        return items
    except Exception as exc:
        print(f"  [WARN] Tavily search failed ({query!r}): {type(exc).__name__}")
        return []


def _add_items_to_mcps(
    items: List[Dict],
    seen_titles: set,
    counts: Dict[str, int],
):
    """Add a list of raw item dicts to the appropriate MCPs, deduplicating by title."""
    for item in items:
        title_key = item["title"][:80].lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        relevance = _india_relevance(item["title"], item["category"])
        content = item.get("content", item["title"])  # Use full content if available

        news_item = NewsItem(
            title=item["title"],
            source=item["source"],
            timestamp=datetime.now().isoformat(),
            content=content,
            category=item["category"],
            relevance_to_india=relevance,
        )

        if item["mcp"] == "india":
            india_news_mcp.add_news_item(news_item)
            counts["india_items"] += 1
        else:
            world_news_mcp.add_news_item(news_item)
            counts["world_items"] += 1


def populate_news_mcps(
    india_feeds: bool = True,
    world_feeds: bool = True,
    max_items_per_feed: int = 8,
    use_tavily: bool = True,
) -> Dict[str, int]:
    """
    Fetch news and populate india_news_mcp and world_news_mcp.

    Data sources (in priority order):
    1. Tavily API — returns article summaries with real content (if TAVILY_API_KEY set)
    2. RSS feeds — headline-only fallback (always runs to fill gaps)

    Args:
        india_feeds: Fetch India business news
        world_feeds: Fetch world news
        max_items_per_feed: Max items per RSS feed
        use_tavily: Attempt Tavily enrichment before RSS (default True)

    Returns:
        Dict with counts: {"india_items": N, "world_items": N, "tavily_used": bool}
    """
    counts: Dict[str, int] = {"india_items": 0, "world_items": 0}
    seen_titles: set = set()
    tavily_used = False

    # ── Tavily enriched search (article summaries, not just headlines) ──────
    client = _get_tavily_client() if use_tavily else None
    if client is not None:
        tavily_queries = []
        if india_feeds:
            tavily_queries += [
                ("India stock market BSE NSE today", "india"),
                ("India economy RBI monetary policy", "india"),
                ("India corporate earnings results", "india"),
            ]
        if world_feeds:
            tavily_queries += [
                ("global markets Fed interest rate outlook", "world"),
                ("crude oil gold prices geopolitical", "world"),
            ]
        for query, mcp_tag in tavily_queries:
            items = fetch_tavily_news(query, mcp_tag=mcp_tag, max_results=5)
            _add_items_to_mcps(items, seen_titles, counts)
        if counts["india_items"] + counts["world_items"] > 0:
            tavily_used = True

    # ── RSS feeds (always run — fills gaps even when Tavily succeeds) ────────
    if FEEDPARSER_AVAILABLE:
        feeds_to_fetch = []
        if india_feeds:
            feeds_to_fetch.extend(INDIA_FEEDS)
        if world_feeds:
            feeds_to_fetch.extend(WORLD_FEEDS)

        for feed_config in feeds_to_fetch:
            items = _fetch_feed(feed_config, max_items=max_items_per_feed)
            _add_items_to_mcps(items, seen_titles, counts)
    elif not tavily_used:
        print("  [WARN] feedparser not installed. Run: pip install feedparser>=6.0.0")

    counts["tavily_used"] = tavily_used  # type: ignore[assignment]
    return counts
