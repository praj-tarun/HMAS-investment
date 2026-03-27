"""
WebSearchUniverseAgent — Phase 2A.

Receives explore_themes from MacroChainAgent, crafts targeted Tavily search
queries for each theme, and extracts candidate NSE tickers from the results.

No fixed ticker list. The universe is entirely driven by:
  1. What macro analysis says is relevant TODAY
  2. What credible financial sources are currently recommending

Returns raw candidates (ticker + source URL) for SourceVerifier to validate.
"""

import re
from typing import Dict, Any, List, Tuple, Optional

from src.core.llm_client import LLMClient

try:
    from src.data.news_fetcher import fetch_tavily_news
    _TAVILY_AVAILABLE = True
except ImportError:
    _TAVILY_AVAILABLE = False

# Fallback sector map — used ONLY if web search returns < 3 candidates
# Not the primary source; just ensures the pipeline never produces zero candidates
_FALLBACK_SECTOR_MAP: Dict[str, List[str]] = {
    "IT":          ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS", "LTIM.NS"],
    "Banking":     ["HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS", "SBIN.NS"],
    "FMCG":        ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS", "DABUR.NS"],
    "Pharma":      ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "LUPIN.NS"],
    "Auto":        ["MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS"],
    "Energy":      ["RELIANCE.NS", "ONGC.NS", "BPCL.NS", "IOC.NS", "GAIL.NS"],
    "Metals":      ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "VEDL.NS"],
    "Defense":     ["HAL.NS", "BEL.NS", "BHEL.NS"],
    "Realty":      ["DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS"],
    "Telecom":     ["BHARTIARTL.NS", "IDEA.NS"],
    "Power":       ["NTPC.NS", "POWERGRID.NS", "TATAPOWER.NS"],
    "Gold":        ["GOLDBEES.NS", "HDFCMFGETF.NS"],
    "Gold ETF":    ["GOLDBEES.NS", "HDFCMFGETF.NS"],
    "Nifty ETF":   ["NIFTYBEES.NS", "SETFNIF50.NS"],
    "Bank ETF":    ["BANKBEES.NS"],
    "IT ETF":      ["ITBEES.NS"],
    "Consumption": ["HINDUNILVR.NS", "ITC.NS", "TITAN.NS", "DMART.NS"],
    "Infra":       ["NTPC.NS", "POWERGRID.NS", "LT.NS", "ADANIPORTS.NS"],
}

_EXTRACTION_SYSTEM = """
You are a financial data extraction assistant. You receive search results about Indian stocks
and your job is to extract valid NSE ticker symbols mentioned in the results.

EXTRACTION RULES:
1. Only extract tickers for companies listed on NSE (National Stock Exchange of India)
2. Format: always append .NS suffix (e.g., INFY.NS, TCS.NS, RELIANCE.NS)
3. Common mappings you know:
   - Infosys → INFY.NS
   - TCS / Tata Consultancy → TCS.NS
   - Reliance Industries → RELIANCE.NS
   - HDFC Bank → HDFCBANK.NS
   - ICICI Bank → ICICIBANK.NS
   - Wipro → WIPRO.NS
   - HCL Tech → HCLTECH.NS
   - Sun Pharma → SUNPHARMA.NS
   - Dr. Reddy's → DRREDDY.NS
   - Maruti / Maruti Suzuki → MARUTI.NS
   - Tata Motors → TATAMOTORS.NS
   - Bajaj Finance → BAJFINANCE.NS
   - Kotak Mahindra Bank → KOTAKBANK.NS
   - Axis Bank → AXISBANK.NS
   - State Bank / SBI → SBIN.NS
   - Bharti Airtel → BHARTIARTL.NS
   - Nifty BeES / NIFTYBEES → NIFTYBEES.NS
   - Gold BeES / GoldBees → GOLDBEES.NS
   - Tata Steel → TATASTEEL.NS
   - ONGC → ONGC.NS
   - NTPC → NTPC.NS
4. If a company name is ambiguous, skip it
5. ETFs must also use .NS suffix

Return ONLY a JSON object:
{
  "tickers": ["TICKER1.NS", "TICKER2.NS", ...],
  "confidence": "high | medium | low"
}
Maximum 15 tickers. No explanation, just the JSON.
"""


def _build_search_queries(theme: str) -> List[str]:
    """Generate 2 targeted search queries for a given theme."""
    theme_lower = theme.lower()

    # Theme-specific query templates
    query_map = {
        "it":         [f"best NSE IT stocks analyst pick FII buying 2025", f"top Indian IT midcap strong dollar beneficiary NSE"],
        "banking":    [f"top NSE banking stocks buy recommendation 2025", f"best Indian private bank stock analyst upgrade"],
        "fmcg":       [f"best NSE FMCG consumer stocks analyst picks 2025", f"top Indian FMCG defensive stocks recession"],
        "pharma":     [f"top NSE pharma export stocks analyst upgrade 2025", f"best Indian pharmaceutical stocks buy recommendation"],
        "auto":       [f"best NSE automobile stocks analyst picks 2025", f"top Indian auto stocks strong rural demand"],
        "energy":     [f"top NSE energy oil gas stocks buy 2025", f"best Indian energy stocks analyst recommendation"],
        "metals":     [f"best NSE metal stocks analyst pick 2025", f"top Indian steel aluminium stocks buy recommendation"],
        "gold":       [f"best gold ETF NSE India highest liquidity 2025", f"top gold fund NSE India investment"],
        "gold etf":   [f"best gold ETF NSE India 2025 liquidity", f"GOLDBEES alternative NSE gold ETF comparison"],
        "nifty etf":  [f"best Nifty 50 index ETF NSE India 2025", f"NIFTYBEES alternatives NSE index fund"],
        "defense":    [f"top NSE defense stocks analyst buy 2025", f"best Indian defense PSU stocks government spending"],
        "power":      [f"top NSE power infrastructure stocks analyst 2025", f"best Indian power utility stocks buy"],
        "infra":      [f"best NSE infrastructure stocks analyst picks 2025", f"top Indian infra capex stocks buy recommendation"],
        "realty":     [f"top NSE real estate stocks analyst 2025", f"best Indian real estate developer stocks"],
        "telecom":    [f"best NSE telecom stocks Bharti Airtel buy 2025", f"top Indian telecom stocks analyst recommendation"],
        "consumption": [f"top NSE consumption domestic demand stocks 2025", f"best Indian consumer discretionary stocks analyst"],
    }

    # Check for a direct match
    for key, queries in query_map.items():
        if key in theme_lower:
            return queries

    # Generic fallback
    return [
        f"best NSE {theme} stocks analyst picks 2025 India",
        f"top Indian {theme} stocks buy recommendation screener",
    ]


class WebSearchUniverseAgent:

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def run(self, explore_themes: List[str]) -> Dict[str, Any]:
        """
        For each explore_theme, search for candidates and extract tickers.

        Returns:
          {
            "raw_candidates": [{"ticker": "INFY.NS", "source_urls": [...], "themes": [...]}, ...],
            "search_queries_used": [...],
            "fallback_used": bool
          }
        """
        if not explore_themes:
            return {"raw_candidates": [], "search_queries_used": [], "fallback_used": False}

        print(f"  [Universe] Searching for candidates in themes: {explore_themes}")

        # Collect search results per theme
        # ticker → {source_urls: set, themes: set, snippets: list}
        ticker_sources: Dict[str, Dict] = {}
        all_queries: List[str] = []

        for theme in explore_themes:
            queries = _build_search_queries(theme)
            all_queries.extend(queries)

            # Collect all search results for this theme, then extract in one LLM call
            theme_results: List[Dict] = []
            for query in queries:
                results = self._search(query)
                theme_results.extend(results)

            if not theme_results:
                continue

            extracted = self._extract_tickers(theme_results, theme)
            for t in extracted["tickers"]:
                if t not in ticker_sources:
                    ticker_sources[t] = {"source_urls": set(), "themes": set(), "snippets": []}
                for r in theme_results:
                    url = r.get("url", "") or r.get("source", "")
                    if url:
                        ticker_sources[t]["source_urls"].add(url)
                ticker_sources[t]["themes"].add(theme)

        # Check if we need fallback
        fallback_used = False
        if len(ticker_sources) < 3:
            print(f"  [Universe] Web search yielded only {len(ticker_sources)} candidates — using fallback sector map")
            fallback_used = True
            for theme in explore_themes:
                for t in _fallback_tickers_for_theme(theme):
                    if t not in ticker_sources:
                        ticker_sources[t] = {"source_urls": set(), "themes": set(), "snippets": []}
                    ticker_sources[t]["themes"].add(theme)
                    ticker_sources[t]["source_urls"].add("fallback://sector_map")

        raw_candidates = [
            {
                "ticker": ticker,
                "source_urls": list(info["source_urls"]),
                "themes": list(info["themes"]),
                "source_count": len(info["source_urls"]),
            }
            for ticker, info in ticker_sources.items()
        ]

        print(f"      -> {len(raw_candidates)} raw candidates from web search")
        return {
            "raw_candidates": raw_candidates,
            "search_queries_used": all_queries,
            "fallback_used": fallback_used,
        }

    def _search(self, query: str) -> List[Dict]:
        """Run one Tavily search query and return result list."""
        if not _TAVILY_AVAILABLE:
            return []
        try:
            items = fetch_tavily_news(query, mcp_tag="india", max_results=6)
            # Include URL in each item for verification
            return items
        except Exception as exc:
            print(f"  [WARN] Search failed ({query!r}): {exc}")
            return []

    def _extract_tickers(self, results: List[Dict], query: str) -> Dict:
        """Use LLM to extract NSE tickers from search results."""
        if not results:
            return {"tickers": [], "confidence": "low"}

        snippets = []
        for r in results:
            title = r.get("title", "")
            content = r.get("content", title)[:200]
            source = r.get("source", "")
            snippets.append(f"[{source}] {title} — {content}")

        user_msg = (
            f"Search query: {query}\n\n"
            f"Search results:\n" +
            "\n".join(f"{i+1}. {s}" for i, s in enumerate(snippets))
        )

        raw = self.llm.reason(
            system_prompt=_EXTRACTION_SYSTEM,
            user_message=user_msg,
            layer="layer1",
            max_tokens=500,
        )
        tickers = raw.get("tickers", [])
        # Ensure .NS suffix
        tickers = [t if t.endswith(".NS") else t + ".NS" for t in tickers if t]
        return {"tickers": tickers, "confidence": raw.get("confidence", "medium")}


def _fallback_tickers_for_theme(theme: str) -> List[str]:
    """Return fallback tickers for a theme from the hardcoded map."""
    theme_lower = theme.lower()
    for key, tickers in _FALLBACK_SECTOR_MAP.items():
        if key.lower() in theme_lower or theme_lower in key.lower():
            return tickers[:4]
    return []
