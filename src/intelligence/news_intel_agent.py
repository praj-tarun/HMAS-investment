"""
NewsIntelAgent — Phase 0 agent for India + world financial headlines.

Data sources:
  - Tavily search (article summaries, most useful)
  - RSS feeds via existing news_fetcher (fallback)

History window: 30 days
"""

from typing import Dict, Any, List

from src.core.llm_client import LLMClient
from src.intelligence.base_intel_agent import BaseIntelAgent

try:
    from src.data.news_fetcher import fetch_tavily_news, populate_news_mcps
    from src.mcp_tools.mcp_tools import india_news_mcp, world_news_mcp
    _NEWS_FETCHER_AVAILABLE = True
except ImportError:
    _NEWS_FETCHER_AVAILABLE = False

_SYSTEM = """
You are the NewsIntelAgent in HMAS v2. Your job is to scan India + world financial
headlines and extract the most market-relevant signals for Indian equities.

You have access to:
1. Today's news headlines and article snippets
2. Your own multi-week history (provided below) — use it to distinguish fresh
   developments from ongoing trends.

ANALYSIS STEPS:
Step 1 — Corporate & Earnings news: Any major earnings beats/misses, guidance changes,
         management commentary, M&A, regulatory actions on companies?
Step 2 — Policy & Regulatory news: RBI, SEBI, MoF, GST council, PLI scheme updates?
Step 3 — Global macro news (India-relevant): Fed commentary, US data, EM flows?
Step 4 — Trend check: Compare with your history — is this a new development or a
         continuing theme? Flag continuations vs new catalysts.

OUTPUT: Valid JSON only:
{
  "summary": "2-3 sentence overview of the most important news this week",
  "key_signals": [
    "signal 1 (max 10 words)",
    "signal 2",
    "signal 3",
    "signal 4",
    "signal 5"
  ],
  "regime": "bullish | bearish | neutral | mixed",
  "confidence": "high | medium | low",
  "new_vs_continuing": {
    "new_catalysts": ["truly fresh developments not seen in history"],
    "continuing_themes": ["trends persisting from previous weeks"]
  },
  "reasoning_chain": [
    "Step 1 — Corporate/Earnings: ...",
    "Step 2 — Policy/Regulatory: ...",
    "Step 3 — Global macro (India-relevant): ...",
    "Step 4 — Trend check: ..."
  ]
}
"""


class NewsIntelAgent(BaseIntelAgent):

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="NewsIntelAgent",
            history_key="news_intel",
            window_days=30,
            llm=llm,
        )

    def _gather_data(self) -> Dict[str, Any]:
        headlines: List[str] = []
        snippets: List[Dict] = []

        if _NEWS_FETCHER_AVAILABLE:
            # Primary: Tavily article summaries
            queries = [
                ("India stock market BSE NSE corporate earnings today", "india"),
                ("India RBI SEBI policy regulation business news", "india"),
                ("global markets India impact Fed interest rates", "world"),
            ]
            for query, tag in queries:
                items = fetch_tavily_news(query, mcp_tag=tag, max_results=5)
                for item in items:
                    text = f"[{item.get('source','')}] {item['title']}"
                    if item.get("content") and item["content"] != item["title"]:
                        text += f" — {item['content'][:150]}"
                    headlines.append(text)
                    snippets.append(item)

            # Fallback: RSS feeds (headline-only, fills gaps)
            if len(headlines) < 10:
                populate_news_mcps(india_feeds=True, world_feeds=True, use_tavily=False)
                for item in india_news_mcp.get_latest_news(10):
                    h = f"[{item.source}] {item.title}"
                    if h not in headlines:
                        headlines.append(h)
                for item in world_news_mcp.get_latest_news(5):
                    h = f"[{item.source}] {item.title}"
                    if h not in headlines:
                        headlines.append(h)

        return {"headlines": headlines[:30], "snippets": snippets}

    def _build_prompt(self, raw_data: Dict[str, Any], history_ctx: str) -> Dict[str, str]:
        headlines = raw_data.get("headlines", [])
        news_block = "\n".join(f"  {i+1}. {h}" for i, h in enumerate(headlines)) or "  No headlines available."

        user = (
            f"TODAY'S NEWS ({len(headlines)} items):\n{news_block}\n\n"
            f"{history_ctx}\n\n"
            "Analyze the news. Compare with your history. Return JSON."
        )
        return {"system": _SYSTEM, "user": user}

    def _parse_result(self, llm_result: Dict[str, Any], raw_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "summary": llm_result.get("summary", "News analysis complete."),
            "key_signals": llm_result.get("key_signals", []),
            "regime": llm_result.get("regime", "neutral"),
            "confidence": llm_result.get("confidence", "medium"),
            "new_vs_continuing": llm_result.get("new_vs_continuing", {}),
            "reasoning_chain": llm_result.get("reasoning_chain", []),
        }
