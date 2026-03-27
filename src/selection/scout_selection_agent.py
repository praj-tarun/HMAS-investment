"""
ScoutSelectionAgent — Phase 4 (Scout mode).

Receives all stock stories from Phase 3, applies scoring and history priority,
selects Top 5, and saves the result to scout_history.json.

Scoring weights (must sum to 100):
  Macro alignment:   30%
  Fundamentals:      25%
  Technical setup:   25%
  Momentum/quant:    20%

Priority boost: +8 points if ticker appeared in scout_history within last 7 days.
This ensures a strong setup identified last week carries continuity.

Model: o3-mini (layer3) for final selection reasoning.
"""

from typing import List, Dict, Any, Optional

from src.core.llm_client import LLMClient
from src.core.types import StockStory, MacroChainOutput
from src.history.scout_history import ScoutHistory

_SYSTEM = """
You are the SelectionAgent in HMAS v2. You receive a list of fully researched stock
investment stories and must select the best 5 opportunities for the week ahead.

SELECTION CRITERIA (in priority order):
1. Macro alignment quality — does the stock directly benefit from the current regime?
   "Direct beneficiary" (e.g., IT exports in a weak rupee regime) scores higher than
   "indirect or neutral" exposure.
2. Fundamental quality — healthy business, reasonable valuation vs peers/history.
   A cheap stock with broken fundamentals is a value trap, not an opportunity.
3. Technical setup — constructive chart increases timing confidence.
   Breakout, support hold, bullish MACD crossover, RSI not overbought.
4. Risk/reward — wide stop relative to entry (poor R:R) downgrades a setup.

HISTORY PRIORITY NOTE:
Some stocks are marked with [HISTORY BOOST: +8 pts]. This means they were in last
week's top 5. A strong setup that was already identified is likely still in play —
honour that continuity unless something has clearly changed.

AVOID THIS WEEK STOCKS:
Stocks in avoid_themes from the macro chain MUST NOT appear in the top 5 unless there
is a compelling stock-specific reason that overrides the macro headwind (rare).

OUTPUT: Valid JSON only:
{
  "top5": [
    {
      "rank": 1,
      "ticker": "INFY.NS",
      "recommendation": "BUY_NOW | WATCH_CLOSELY | MONITOR_FOR_LATER",
      "conviction": "high | medium | low",
      "final_score": 84,
      "score_breakdown": {
        "macro_alignment": 27,
        "fundamentals": 22,
        "technical_setup": 21,
        "momentum": 14,
        "history_boost": 0
      },
      "story": "The complete investment narrative from the research agent",
      "entry_zone": "price range",
      "stop_loss": "stop level",
      "time_horizon": "holding period",
      "key_risk": "top risk",
      "why_selected": "one sentence: the single most important reason this made the top 5"
    }
  ],
  "avoided": ["TICKER1.NS", "TICKER2.NS"],
  "avoided_reasons": {"TICKER1.NS": "macro headwind: Banking in rate-hold environment"},
  "selection_reasoning": [
    "Overall regime: ...",
    "Ranking rationale: ...",
    "Key trade-offs considered: ..."
  ]
}
"""


def _format_stories_for_prompt(
    stories: List[StockStory],
    history_tickers: set,
    avoid_themes: List[str],
) -> str:
    lines = ["## STOCK STORIES FOR SELECTION\n"]
    for s in stories:
        boost_flag = " [HISTORY BOOST: +8 pts]" if s.ticker in history_tickers else ""
        lines.append(
            f"### {s.ticker} — Score: {s.score}/100{boost_flag}\n"
            f"Conviction: {s.conviction}  |  Type: {s.opportunity_type}\n"
            f"Story: {s.story}\n"
            f"Macro alignment: {s.macro_alignment}\n"
            f"Technicals: {s.technicals_summary}\n"
            f"Fundamentals: {s.fundamentals_summary}\n"
            f"Entry: {s.entry_zone}  |  Stop: {s.stop_loss}  |  Horizon: {s.time_horizon}\n"
            f"Key risk: {s.key_risk}\n"
        )
    if avoid_themes:
        lines.append(f"\n## AVOID THEMES (from macro chain): {', '.join(avoid_themes)}")
    return "\n".join(lines)


class ScoutSelectionAgent:

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.scout_history = ScoutHistory()

    def run(
        self,
        stories: List[StockStory],
        macro_chain: MacroChainOutput,
    ) -> Dict[str, Any]:
        """
        Select top 5 from the researched stories.

        Returns dict with top5 list, avoided tickers, and selection reasoning.
        Also saves the selection to scout_history.json.
        """
        if not stories:
            return {"top5": [], "avoided": [], "selection_reasoning": ["No stories provided."]}

        # Apply history boost to scores
        history_tickers = self.scout_history.tickers_in_window(days=7)
        boosted_stories = []
        for s in stories:
            boosted = s
            if s.ticker in history_tickers:
                # Create a copy with boosted score
                import dataclasses
                boosted = dataclasses.replace(s, score=min(100, s.score + 8))
            boosted_stories.append(boosted)

        # Sort by score descending (pre-sort hint for LLM)
        boosted_stories.sort(key=lambda x: x.score, reverse=True)

        prompt_block = _format_stories_for_prompt(
            boosted_stories, history_tickers, macro_chain.avoid_themes
        )

        user_msg = (
            f"## MACRO CONTEXT\n{macro_chain.summary_for_prompt()}\n\n"
            f"## SCOUT HISTORY (last 4 runs)\n{self.scout_history.recent_runs_summary(4)}\n\n"
            + prompt_block +
            "\n\nSelect the best 5. Apply the scoring and history priority rules. Return JSON."
        )

        raw = self.llm.reason(
            system_prompt=_SYSTEM,
            user_message=user_msg,
            layer="layer3",
            max_tokens=4000,
        )

        top5 = raw.get("top5", [])

        # Fallback: if LLM returned empty top5 but we have valid stories,
        # auto-rank by score so the user always gets actionable output
        if not top5 and boosted_stories:
            print("  [WARN] Selection LLM returned empty top5 — using score-ranked fallback")
            candidates = [s for s in boosted_stories if s.opportunity_type != "error"]
            candidates.sort(key=lambda s: s.score, reverse=True)
            for i, s in enumerate(candidates[:5], 1):
                rec = "WATCH_CLOSELY" if s.score >= 60 else "MONITOR_FOR_LATER"
                top5.append({
                    "rank": i,
                    "ticker": s.ticker,
                    "recommendation": rec,
                    "conviction": s.conviction,
                    "final_score": round(s.score),
                    "score_breakdown": {},
                    "story": s.story,
                    "entry_zone": s.entry_zone,
                    "stop_loss": s.stop_loss,
                    "time_horizon": s.time_horizon,
                    "key_risk": s.key_risk,
                    "why_selected": f"Score-ranked fallback (score {s.score:.0f}/100) — "
                                    f"{s.opportunity_type}, {s.macro_alignment[:80]}",
                })

        # Save to scout history
        top5_tickers = [item.get("ticker", "") for item in top5 if item.get("ticker")]
        self.scout_history.record_run(
            top5=top5_tickers,
            regime=macro_chain.market_regime,
        )

        return {
            "top5": top5,
            "avoided": raw.get("avoided", []),
            "avoided_reasons": raw.get("avoided_reasons", {}),
            "selection_reasoning": raw.get("selection_reasoning", []),
            "history_boost_applied_to": sorted(history_tickers & {s.ticker for s in stories}),
        }
