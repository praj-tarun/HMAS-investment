"""
StockResearchAgent — Phase 3 (Scout mode).

Produces a full investment "story" for a single NSE ticker:
  - Macro alignment: how does the current regime affect THIS stock specifically
  - Technical setup: is the chart constructive?
  - Fundamental quality: is it priced right? is the business healthy?
  - A scored composite view
  - Entry zone, stop loss, time horizon

Uses history cache: if < 7 days old, loads previous analysis as base
and only refreshes technicals + latest news.

Model: gpt-4o (layer2) for story synthesis.
"""

from typing import Dict, Any, Optional

from src.core.llm_client import LLMClient
from src.core.types import StockStory, MacroChainOutput
from src.history.stock_history import StockHistory
from src.research.base_research_agent import fetch_live_data, fetch_stock_news, format_data_block

_SYSTEM = """
You are a senior equity research analyst building an investment case for a retail investor
in India. You will receive:
  - Live price and technical data
  - Fundamental metrics
  - Recent company/sector news
  - The current macro regime and causal chain

YOUR JOB: Write a complete, actionable investment story for this stock.

STORY QUALITY RULES:
1. Be specific — name the mechanism, not just the direction
   GOOD: "Infosys earns in USD; INR at 84.8 means each dollar of revenue is worth ₹84.8
         vs ₹80 six months ago — a 6% tail wind to rupee earnings with zero operational change"
   BAD:  "IT stocks benefit from rupee weakness"

2. Connect macro to this specific stock's business model
3. Technicals must reference actual levels (MA50, RSI value, MACD state)
4. Entry zone must be realistic relative to current price
5. Conviction must reflect the evidence quality — don't grade everything "high"
6. Score 0-100 using these weights:
   - Macro alignment: 30 pts (how directly does the macro regime help/hurt THIS stock?)
   - Fundamental quality: 25 pts (business health, valuation vs peers)
   - Technical setup: 25 pts (constructive chart? near support? breakout?)
   - Momentum/quant: 20 pts (price momentum, volume, 52W position)

OUTPUT: Valid JSON only:
{
  "company_name": "full company name",
  "story": "3-5 sentence investment narrative connecting macro regime to this stock's opportunity",
  "opportunity_type": "macro_tailwind | value_play | momentum | defensive | avoid",
  "entry_zone": "price range e.g. ₹1,820–1,850 or 'Current levels' or 'AVOID'",
  "stop_loss": "price level and what it represents e.g. ₹1,740 (below 200-DMA)",
  "time_horizon": "expected holding period e.g. 4-6 weeks",
  "conviction": "high | medium | low",
  "score": 72,
  "key_risk": "single most important risk that could invalidate this setup",
  "macro_alignment": "one sentence: how this stock specifically relates to the current macro regime",
  "technicals_summary": "RSI 58, MACD bullish crossover, above MA50 and MA200",
  "fundamentals_summary": "PE 22x (below 5Y avg 25x), ROE 31%, low debt, revenue growth accelerating",
  "news_highlights": ["brief highlight 1", "brief highlight 2"],
  "reasoning_chain": [
    "Macro alignment (30pts): ...",
    "Fundamental quality (25pts): ...",
    "Technical setup (25pts): ...",
    "Momentum/quant (20pts): ...",
    "Score: X/100 → conviction: ..."
  ]
}
"""


class StockResearchAgent:

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.stock_history = StockHistory(ttl_days=7)

    def run(self, ticker: str, macro_chain: MacroChainOutput) -> StockStory:
        """
        Build a full investment story for `ticker` given the current macro context.
        Returns a StockStory dataclass.
        """
        # Check cache
        cached = self.stock_history.get(ticker)
        from_cache = cached is not None
        cached_ctx = ""
        if cached:
            cached_ctx = self.stock_history.get_context_for_prompt(ticker)

        # Always fetch fresh live data (prices change daily)
        live = fetch_live_data(ticker)
        company_name = live.get("company_name", ticker.replace(".NS", ""))

        # Fetch news (reduced set if using cache)
        news = fetch_stock_news(ticker, company_name, max_results=4 if cached else 6)

        # Build prompt
        data_block = format_data_block(
            ticker=ticker,
            live=live,
            news=news,
            macro_summary=macro_chain.summary_for_prompt(),
            cached_context=cached_ctx,
        )

        raw = self.llm.reason(
            system_prompt=_SYSTEM,
            user_message=data_block + "\n\nWrite the full investment story and score this stock. Return JSON.",
            layer="layer2",
            max_tokens=2000,
        )

        story = StockStory(
            ticker=ticker,
            company_name=raw.get("company_name", company_name),
            story=raw.get("story", "Analysis complete."),
            opportunity_type=raw.get("opportunity_type", "unknown"),
            entry_zone=raw.get("entry_zone", "N/A"),
            stop_loss=raw.get("stop_loss", "N/A"),
            time_horizon=raw.get("time_horizon", "N/A"),
            conviction=raw.get("conviction", "low"),
            score=float(raw.get("score", 50)),
            key_risk=raw.get("key_risk", ""),
            macro_alignment=raw.get("macro_alignment", ""),
            technicals_summary=raw.get("technicals_summary", ""),
            fundamentals_summary=raw.get("fundamentals_summary", ""),
            news_highlights=raw.get("news_highlights", []),
            reasoning_chain=raw.get("reasoning_chain", []),
            from_cache=from_cache,
        )

        # Save to history (overwrites previous)
        self.stock_history.save(ticker, story.to_dict())
        return story
