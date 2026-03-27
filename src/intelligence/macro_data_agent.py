"""
MacroDataAgent — Phase 0 agent for macroeconomic indicators.

Tracks: Brent crude, Gold, WTI, US 10Y yield, India 10Y yield (proxy),
        USD/INR, DXY, VIX (as volatility proxy for risk premium)
Data source: yfinance for live prices + Tavily for CPI/RBI/Fed commentary
History window: 180 days (macro trends are slow-moving)
"""

from typing import Dict, Any

from src.core.llm_client import LLMClient
from src.intelligence.base_intel_agent import BaseIntelAgent

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

try:
    from src.data.news_fetcher import fetch_tavily_news
    _FETCHER_AVAILABLE = True
except ImportError:
    _FETCHER_AVAILABLE = False

# Macro commodity and rate tickers
_MACRO_TICKERS = {
    "Brent_Crude":  "BZ=F",
    "WTI_Crude":    "CL=F",
    "Gold":         "GC=F",
    "Silver":       "SI=F",
    "USD_INR":      "USDINR=X",
    "DXY":          "DX-Y.NYB",
    "US_10Y_Yield": "^TNX",
    "VIX":          "^VIX",
}

_SYSTEM = """
You are the MacroDataAgent in HMAS v2. Your specialization is reading macroeconomic
indicators and building an India-specific macro picture.

You have:
1. Live prices for commodities (crude, gold), FX (USD/INR, DXY), and rates (US 10Y yield)
2. Recent news headlines about RBI, Fed, CPI, inflation
3. Your 6-month rolling history — crucial for trend detection

KEY RELATIONSHIPS TO REASON ABOUT:
  Crude oil  → India's import bill, CAD, rupee, RBI policy room, inflation
  Gold       → Safe-haven signal, inverse of risk appetite, inflation hedge
  DXY / USD  → Rupee pressure, FII equity flows, EM risk appetite
  US 10Y     → Dollar strength driver, cost of capital globally, PE multiple compression
  VIX        → Risk appetite proxy, EM capital flows

ANALYSIS STEPS:
Step 1 — Commodity prices: Where is crude relative to the 3M/6M average? Is this
         a sustained move or a spike? What does this mean for India's import bill?
Step 2 — Currency & dollar: DXY trend. USD/INR trajectory. Is the rupee breaking
         out of a range or holding?
Step 3 — Rates & risk: US 10Y direction. VIX level. Are we in a tightening or
         easing cycle globally?
Step 4 — RBI/Fed signals from news: Any rate decisions, minutes, CPI data that
         shifts the policy outlook?
Step 5 — Trend check: What has been consistently true over 4+ weeks vs what changed
         this week?

OUTPUT: Valid JSON only:
{
  "summary": "2-3 sentence macro overview for India: what the indicators collectively mean",
  "key_signals": ["signal 1", "signal 2", "signal 3", "signal 4", "signal 5"],
  "regime": "inflationary-tightening | disinflationary-easing | stagflation | goldilocks | mixed",
  "confidence": "high | medium | low",
  "india_macro_read": {
    "crude_impact": "one-line: crude level and India CAD/inflation implication",
    "rupee_outlook": "stable | under-pressure | appreciating | volatile",
    "rbi_room": "rate-cut-possible | on-hold | rate-hike-risk",
    "pe_pressure": "compressing | stable | expanding"
  },
  "data_snapshot": {},
  "reasoning_chain": [
    "Step 1 — Crude: ...",
    "Step 2 — Currency/Dollar: ...",
    "Step 3 — Rates/Risk: ...",
    "Step 4 — RBI/Fed news: ...",
    "Step 5 — Trend check: ..."
  ]
}
"""


def _fetch_macro_prices() -> Dict[str, Any]:
    """Fetch current prices and trends for macro indicators."""
    result: Dict[str, Any] = {}
    if not _YF_AVAILABLE:
        return result
    for name, symbol in _MACRO_TICKERS.items():
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="3mo")
            if hist.empty:
                continue
            closes = hist["Close"].tolist()
            current = round(closes[-1], 4)
            avg_30d = round(sum(closes[-30:]) / min(30, len(closes)), 4)
            avg_90d = round(sum(closes) / len(closes), 4)
            chg_5d = round(((closes[-1] - closes[-5]) / closes[-5]) * 100, 2) if len(closes) >= 5 else 0.0
            chg_30d = round(((closes[-1] - closes[-30]) / closes[-30]) * 100, 2) if len(closes) >= 30 else 0.0
            result[name] = {
                "current": current,
                "avg_30d": avg_30d,
                "avg_90d": avg_90d,
                "chg_5d_pct": chg_5d,
                "chg_30d_pct": chg_30d,
                "vs_30d_avg": "above" if current > avg_30d else "below",
            }
        except Exception:
            pass
    return result


class MacroDataAgent(BaseIntelAgent):

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="MacroDataAgent",
            history_key="macro_data",
            window_days=180,
            llm=llm,
        )

    def _gather_data(self) -> Dict[str, Any]:
        prices = _fetch_macro_prices()

        news_headlines = []
        if _FETCHER_AVAILABLE:
            for q, tag in [
                ("RBI monetary policy rate decision inflation India 2025", "india"),
                ("Federal Reserve interest rate CPI inflation outlook 2025", "world"),
                ("crude oil price OPEC outlook 2025", "world"),
            ]:
                items = fetch_tavily_news(q, mcp_tag=tag, max_results=3)
                for item in items:
                    text = f"[{item.get('source','')}] {item['title']}"
                    if item.get("content") and item["content"] != item["title"]:
                        text += f" — {item['content'][:100]}"
                    if text not in news_headlines:
                        news_headlines.append(text)

        return {"prices": prices, "news_headlines": news_headlines[:15]}

    def _build_prompt(self, raw_data: Dict[str, Any], history_ctx: str) -> Dict[str, str]:
        prices = raw_data.get("prices", {})
        news = raw_data.get("news_headlines", [])

        price_rows = []
        for name, vals in prices.items():
            price_rows.append(
                f"  {name:<16} current={vals.get('current','N/A')}  "
                f"5d={vals.get('chg_5d_pct',0):+.2f}%  "
                f"30d={vals.get('chg_30d_pct',0):+.2f}%  "
                f"vs30d_avg={vals.get('vs_30d_avg','?')}"
            )
        price_block = "\n".join(price_rows) if price_rows else "  No price data (yfinance unavailable)."
        news_block = "\n".join(f"  {h}" for h in news) if news else "  No macro news."

        user = (
            f"MACRO INDICATORS:\n{price_block}\n\n"
            f"MACRO NEWS:\n{news_block}\n\n"
            f"{history_ctx}\n\n"
            "Build the India macro picture. Return JSON."
        )
        return {"system": _SYSTEM, "user": user}

    def _parse_result(self, llm_result: Dict[str, Any], raw_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "summary": llm_result.get("summary", "Macro data analysis complete."),
            "key_signals": llm_result.get("key_signals", []),
            "regime": llm_result.get("regime", "mixed"),
            "confidence": llm_result.get("confidence", "medium"),
            "india_macro_read": llm_result.get("india_macro_read", {}),
            "data_snapshot": raw_data.get("prices", {}),
            "reasoning_chain": llm_result.get("reasoning_chain", []),
        }
