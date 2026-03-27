"""
GeopoliticsAgent — Phase 0 agent for geopolitical events affecting India/EM markets.

Covers: wars, OPEC decisions, sanctions, elections, trade deals, tariffs
Data source: Tavily search + RSS world news
History window: 90 days (geopolitical events are slow-moving)
"""

from typing import Dict, Any, List

from src.core.llm_client import LLMClient
from src.intelligence.base_intel_agent import BaseIntelAgent

try:
    from src.data.news_fetcher import fetch_tavily_news
    _FETCHER_AVAILABLE = True
except ImportError:
    _FETCHER_AVAILABLE = False

_SYSTEM = """
You are the GeopoliticsAgent in HMAS v2. Your specialization is identifying geopolitical
events that have a direct transmission mechanism to Indian equity markets.

INDIA TRANSMISSION CHANNELS (use these to filter relevance):
  Oil channel:       OPEC decisions, Middle East conflicts, Russia/Ukraine → crude price → India CAD
  Dollar channel:    US policy, Fed signals, EM risk appetite → USD/INR → FII flows
  Trade channel:     US/China tariffs, sanctions → India IT/Pharma exports
  EM sentiment:      China slowdown, EM crises, global risk-off → India capital flows
  Direct India:      India-Pakistan tensions, India-China border, Indian elections, GST/policy

FILTER RULE: Only include events with a clear transmission mechanism to Indian markets.
A conflict in South America with no India link → EXCLUDE.
OPEC production cut → INCLUDE (oil channel, directly impacts India CAD).

You have your rolling history — compare today's events with prior ones.
Flag: new escalations, de-escalations, and stalled situations.

OUTPUT: Valid JSON only:
{
  "summary": "2-3 sentence geopolitical overview and India impact",
  "key_signals": ["signal 1", "signal 2", "signal 3", "signal 4", "signal 5"],
  "regime": "elevated-risk | moderate-risk | calm",
  "confidence": "high | medium | low",
  "india_transmission": {
    "oil_channel": "active | inactive",
    "dollar_channel": "active | inactive",
    "trade_channel": "active | inactive",
    "direct_india": "active | inactive"
  },
  "active_events": [
    {
      "event": "event name",
      "status": "new | escalating | continuing | de-escalating",
      "india_impact": "one-line India market impact"
    }
  ],
  "reasoning_chain": [
    "Step 1 — Filter and relevant events: ...",
    "Step 2 — Transmission channels: ...",
    "Step 3 — Trend vs prior history: ..."
  ]
}
"""


class GeopoliticsAgent(BaseIntelAgent):

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="GeopoliticsAgent",
            history_key="geopolitics",
            window_days=90,
            llm=llm,
        )

    def _gather_data(self) -> Dict[str, Any]:
        headlines: List[str] = []

        if _FETCHER_AVAILABLE:
            queries = [
                ("OPEC oil production geopolitical conflict Middle East 2025", "world"),
                ("US China trade war tariffs sanctions India impact", "world"),
                ("India geopolitics border economy policy 2025", "india"),
                ("global geopolitical risk emerging markets", "world"),
            ]
            for query, tag in queries:
                items = fetch_tavily_news(query, mcp_tag=tag, max_results=4)
                for item in items:
                    text = f"[{item.get('source','')}] {item['title']}"
                    if item.get("content") and item["content"] != item["title"]:
                        text += f" — {item['content'][:120]}"
                    if text not in headlines:
                        headlines.append(text)

        return {"headlines": headlines[:25]}

    def _build_prompt(self, raw_data: Dict[str, Any], history_ctx: str) -> Dict[str, str]:
        headlines = raw_data.get("headlines", [])
        news_block = "\n".join(f"  {i+1}. {h}" for i, h in enumerate(headlines)) or "  No geopolitical news available."

        user = (
            f"GEOPOLITICAL NEWS ({len(headlines)} items):\n{news_block}\n\n"
            f"{history_ctx}\n\n"
            "Filter for India-relevant events only. Assess transmission channels. Return JSON."
        )
        return {"system": _SYSTEM, "user": user}

    def _parse_result(self, llm_result: Dict[str, Any], raw_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "summary": llm_result.get("summary", "Geopolitics analysis complete."),
            "key_signals": llm_result.get("key_signals", []),
            "regime": llm_result.get("regime", "moderate-risk"),
            "confidence": llm_result.get("confidence", "medium"),
            "india_transmission": llm_result.get("india_transmission", {}),
            "active_events": llm_result.get("active_events", []),
            "reasoning_chain": llm_result.get("reasoning_chain", []),
        }
