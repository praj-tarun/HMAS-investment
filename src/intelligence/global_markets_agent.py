"""
GlobalMarketsAgent — Phase 0 agent for world market indices, FX, yields, FII flows.

Tracks: S&P 500, Nasdaq, Nifty 50, USD/INR, DXY, VIX, 10Y UST, Hang Seng, Nikkei, DAX
Data source: yfinance (direct, not via global MCPs)
History window: 30 days
"""

from typing import Dict, Any

from src.core.llm_client import LLMClient
from src.intelligence.base_intel_agent import BaseIntelAgent

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

# yfinance tickers for global market tracking
_GLOBAL_TICKERS = {
    "S&P500":    "^GSPC",
    "Nasdaq":    "^IXIC",
    "Nifty50":   "^NSEI",
    "USD/INR":   "USDINR=X",
    "DXY":       "DX-Y.NYB",
    "VIX":       "^VIX",
    "10Y_UST":   "^TNX",
    "HangSeng":  "^HSI",
    "Nikkei":    "^N225",
    "DAX":       "^GDAXI",
    "Gold":      "GC=F",
    "Brent":     "BZ=F",
}

_SYSTEM = """
You are the GlobalMarketsAgent in HMAS v2. Your specialization is reading world market
data and translating it into signals for Indian equity investors.

You have:
1. Today's live price levels and weekly % changes for global indices, FX, and rates
2. Your rolling history — use it to identify multi-week trends vs one-day noise

ANALYSIS STEPS:
Step 1 — Risk appetite: Are global markets risk-on or risk-off? Look at VIX, S&P 500
         direction, EM vs DM performance split.
Step 2 — Dollar & rupee pressure: DXY trend + USD/INR level. Stronger dollar = more
         pressure on Indian equities via FII outflows and import cost inflation.
Step 3 — Rates impact: US 10Y yield direction. Rising yields = dollar strength +
         compression of Indian equity PE multiples + FII allocation shifts.
Step 4 — FII flow proxy: Nifty vs global peers. If Nifty underperforms S&P 500
         significantly, FII are likely net sellers in India.
Step 5 — Trend check: Are these levels a continuation of prior weeks or a new break?

OUTPUT: Valid JSON only:
{
  "summary": "2-3 sentence overview of global market posture and its India impact",
  "key_signals": ["signal 1", "signal 2", "signal 3", "signal 4", "signal 5"],
  "regime": "risk-on | risk-off | mixed",
  "confidence": "high | medium | low",
  "fii_flow_outlook": "net-buyers | net-sellers | neutral",
  "rupee_pressure": "high | moderate | low",
  "market_data_snapshot": {},
  "reasoning_chain": [
    "Step 1 — Risk appetite: ...",
    "Step 2 — Dollar/rupee: ...",
    "Step 3 — Rates impact: ...",
    "Step 4 — FII proxy: ...",
    "Step 5 — Trend check: ..."
  ]
}
"""


def _safe_fetch(ticker_map: Dict[str, str]) -> Dict[str, Any]:
    """Fetch latest price + 5-day change for each ticker. Returns flat dict."""
    result: Dict[str, Any] = {}
    if not _YF_AVAILABLE:
        return result
    for name, symbol in ticker_map.items():
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="10d")
            if hist.empty:
                continue
            closes = hist["Close"].tolist()
            current = round(closes[-1], 4)
            chg_5d = round(((closes[-1] - closes[-5]) / closes[-5]) * 100, 2) if len(closes) >= 5 else 0.0
            chg_1d = round(((closes[-1] - closes[-2]) / closes[-2]) * 100, 2) if len(closes) >= 2 else 0.0
            result[name] = {"current": current, "chg_1d_pct": chg_1d, "chg_5d_pct": chg_5d}
        except Exception:
            pass
    return result


class GlobalMarketsAgent(BaseIntelAgent):

    def __init__(self, llm: LLMClient):
        super().__init__(
            name="GlobalMarketsAgent",
            history_key="global_markets",
            window_days=30,
            llm=llm,
        )

    def _gather_data(self) -> Dict[str, Any]:
        return {"market_data": _safe_fetch(_GLOBAL_TICKERS)}

    def _build_prompt(self, raw_data: Dict[str, Any], history_ctx: str) -> Dict[str, str]:
        mkt = raw_data.get("market_data", {})

        rows = []
        for name, vals in mkt.items():
            rows.append(
                f"  {name:<12} current={vals.get('current','N/A')}  "
                f"1d={vals.get('chg_1d_pct',0):+.2f}%  "
                f"5d={vals.get('chg_5d_pct',0):+.2f}%"
            )
        data_block = "\n".join(rows) if rows else "  No market data available (yfinance may be unavailable)."

        user = (
            f"GLOBAL MARKET DATA (today):\n{data_block}\n\n"
            f"{history_ctx}\n\n"
            "Analyze the market posture and its India impact. Return JSON."
        )
        return {"system": _SYSTEM, "user": user}

    def _parse_result(self, llm_result: Dict[str, Any], raw_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "summary": llm_result.get("summary", "Global markets analysis complete."),
            "key_signals": llm_result.get("key_signals", []),
            "regime": llm_result.get("regime", "mixed"),
            "confidence": llm_result.get("confidence", "medium"),
            "fii_flow_outlook": llm_result.get("fii_flow_outlook", "neutral"),
            "rupee_pressure": llm_result.get("rupee_pressure", "moderate"),
            "market_data_snapshot": raw_data.get("market_data", {}),
            "reasoning_chain": llm_result.get("reasoning_chain", []),
        }
