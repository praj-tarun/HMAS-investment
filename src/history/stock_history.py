"""
StockHistory — per-ticker analysis cache with a 7-day TTL.

On each StockResearchAgent run:
  1. Check if a fresh analysis (< TTL days) exists → return it as base context
  2. After new analysis, overwrite with fresh data

This prevents re-fetching and re-reasoning the same stock on consecutive days
(fundamentals don't change daily). Technicals are always refreshed on top of
the cached base.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

_STOCK_DIR = Path(__file__).parent.parent.parent / "data" / "stock_history"
_DEFAULT_TTL_DAYS = 7


class StockHistory:
    """
    Cache manager for individual stock analyses.

    Usage:
        sh = StockHistory()
        cached = sh.get("INFY.NS")   # None if stale/missing
        sh.save("INFY.NS", story_dict)
    """

    def __init__(self, ttl_days: int = _DEFAULT_TTL_DAYS):
        self.ttl_days = ttl_days
        _STOCK_DIR.mkdir(parents=True, exist_ok=True)

    def get(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Return cached analysis if it exists and is within TTL, else None.

        The caller should use the cached data as base context and layer
        fresh technicals/price on top of it.
        """
        path = self._path(ticker)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            last_updated = data.get("last_updated", "")
            if not last_updated:
                return None
            age = datetime.now() - datetime.fromisoformat(last_updated)
            if age > timedelta(days=self.ttl_days):
                return None  # Stale
            return data
        except Exception:
            return None

    def save(self, ticker: str, analysis: Dict[str, Any]) -> None:
        """Overwrite (or create) the cached analysis for a ticker."""
        analysis["last_updated"] = datetime.now().isoformat()
        analysis["ticker"] = ticker
        try:
            with open(self._path(ticker), "w", encoding="utf-8") as f:
                json.dump(analysis, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"  [WARN] StockHistory.save({ticker}) failed: {exc}")

    def get_context_for_prompt(self, ticker: str) -> str:
        """
        Return a compact string for injecting into a research agent prompt.
        Indicates if there's recent analysis or not.
        """
        cached = self.get(ticker)
        if not cached:
            return f"No prior analysis cached for {ticker}. Perform full fresh analysis."
        age_days = (datetime.now() - datetime.fromisoformat(cached["last_updated"])).days
        lines = [
            f"## Prior Analysis for {ticker} ({age_days} days ago)",
            f"Score: {cached.get('score', 'N/A')}  |  Conviction: {cached.get('conviction', 'N/A')}",
            f"Story summary: {cached.get('story', '')[:200]}",
            f"Entry zone: {cached.get('entry_zone', 'N/A')}  |  Stop: {cached.get('stop_loss', 'N/A')}",
        ]
        fundamentals = cached.get("fundamentals", {})
        if fundamentals:
            lines.append(
                f"Fundamentals: PE={fundamentals.get('pe','N/A')}  PB={fundamentals.get('pb','N/A')}  "
                f"ROE={fundamentals.get('roe','N/A')}%"
            )
        lines.append(
            "NOTE: Refresh technicals and recent news. Reuse fundamental thesis if still valid."
        )
        return "\n".join(lines)

    def list_cached(self) -> Dict[str, str]:
        """Return {ticker: last_updated} for all cached stocks."""
        result = {}
        for path in _STOCK_DIR.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                ticker = data.get("ticker", path.stem)
                result[ticker] = data.get("last_updated", "unknown")
            except Exception:
                pass
        return result

    def _path(self, ticker: str) -> Path:
        # Sanitize ticker for filename: INFY.NS → INFY.NS.json
        safe = ticker.replace("/", "_").replace("\\", "_")
        return _STOCK_DIR / f"{safe}.json"
