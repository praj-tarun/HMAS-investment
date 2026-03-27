"""
HoldingResearchAgent — Phase 3 (Portfolio mode).

Like StockResearchAgent but adds portfolio-specific context:
  - Entry price, current price, unrealized P&L%
  - Days held
  - Original thesis validation (does current data confirm or contradict it?)
  - Blank-slate test (would a fresh buyer buy today?)
  - Exit condition check

Uses the same 7-day stock history cache as StockResearchAgent
(reuses analysis if scout already ran this ticker today).

Model: gpt-4o (layer2) for story synthesis.
"""

from typing import Dict, Any

from src.core.llm_client import LLMClient
from src.core.types import HoldingAction, MacroChainOutput
from src.history.stock_history import StockHistory
from src.research.base_research_agent import fetch_live_data, fetch_stock_news, format_data_block

_SYSTEM = """
You are a senior portfolio manager reviewing a retail investor's existing holding.
The investor is a LONG-TERM holder (1+ years) looking for practical, forward-looking guidance —
not just a snapshot verdict. They want to know the BEST MOVE given where they are today,
what recovery looks like, and what specific conditions should trigger action.

You will receive:
  - Live technical data for the proxy ETF (for direction signals only)
  - The actual MF/ETF P&L from the investor's statement
  - Recent macro regime and sector news
  - Entry date, P&L, original thesis, exit condition

YOUR JOB: Give the investor the most useful forward-looking recommendation possible.
"EXIT everything" when equities are down is NOT useful advice — it locks in losses.
"HOLD forever" ignoring macro risk is also not useful. Find the specific, reasoned middle ground.

MANDATORY ANALYSIS:
1. THESIS CHECK: Is the core reason for holding still valid?
   - For MF/ETF holdings: is the underlying sector/index story structurally intact?
   - Name what has changed and what hasn't.

2. RECOVERY SCENARIO: What does the path back to breakeven look like?
   - How far is the holding from cost price (% needed to recover)?
   - What macro/technical conditions would trigger that recovery?
   - Realistic timeframe (months, not "when market recovers")

3. CURRENT PRICE CONTEXT: Is this a bad time to exit?
   - Is the holding near a support level or already bounced?
   - Exiting at the bottom of a drawdown locks in loss — state this explicitly if relevant.

4. FORWARD TRIGGERS — be specific:
   - What would make you UPGRADE to ADD? (e.g., "FII outflows stabilise, RSI > 50")
   - What would make you DOWNGRADE to EXIT? (e.g., "index breaks 200-DMA, no RBI rate cut in 6 months")

ACTION DEFINITIONS:
  HOLD:         Thesis intact, current price is in a drawdown — waiting for recovery is rational.
  ADD / SIP:    Thesis intact + current price is at/near support = averaging opportunity.
  TRIM:         Take partial profits OR reduce overweight exposure — not a panic exit.
  HOLD_WATCH:   Thesis weakening but not broken. Set a specific price/time stop and wait.
  EXIT:         Thesis structurally broken (not just cyclically down) OR better alternative exists
                that makes capital more productive. EXIT requires naming WHERE to redeploy.

IMPORTANT: For a holding that is cyclically down in a risk-off environment:
- "Risk-off" is a phase, not permanent. Distinguish cyclical headwinds from structural breaks.
- Recommending EXIT during maximum fear often destroys value. Consider HOLD or TRIM instead.
- If EXIT is warranted, state specifically what the investor should do with the proceeds.

OUTPUT: Valid JSON only:
{
  "action": "HOLD | ADD | TRIM | HOLD_WATCH | EXIT",
  "narrative": "4-6 sentence explanation: where we are, why this action, what to watch",
  "thesis_status": "intact | weakening | broken",
  "thesis_validation_note": "what in the original thesis still holds, what has changed",
  "blank_slate_test": "PASS | FAIL",
  "blank_slate_note": "if FAIL: acknowledge it but also explain if this is cyclical vs structural",
  "recovery_scenario": "how far from breakeven, what conditions trigger recovery, rough timeframe",
  "upgrade_trigger": "specific condition that would make you ADD/SIP more",
  "downgrade_trigger": "specific condition that would make you EXIT",
  "macro_alignment": "how current macro regime affects this holding — cyclical or structural impact?",
  "technicals_summary": "RSI, MACD, MA position — is this near support or breaking down?",
  "fundamentals_summary": "sector fundamentals — is the underlying story intact?",
  "exit_condition_status": "not triggered | approaching | triggered",
  "key_risk": "single most important risk going forward",
  "news_highlights": ["highlight 1", "highlight 2"],
  "reasoning_chain": [
    "1. Thesis check: ...",
    "2. Recovery scenario: ...",
    "3. Current price context (good/bad time to act): ...",
    "4. Macro overlay — cyclical or structural: ...",
    "5. Action with specific forward triggers: ..."
  ]
}
"""


class HoldingResearchAgent:

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.stock_history = StockHistory(ttl_days=7)

    def run(self, holding: Dict[str, Any], macro_chain: MacroChainOutput, previous_context: str = "") -> HoldingAction:
        """
        Analyse a portfolio holding and return an action recommendation.

        Args:
            holding:     Dict from portfolio_memory with ticker, entry_price,
                         current_price, unrealized_pnl_pct, thesis, exit_condition
            macro_chain: MacroChainOutput from Phase 1
        """
        ticker = holding.get("ticker", "UNKNOWN")
        entry_price = holding.get("entry_price", 0)
        entry_date = holding.get("entry_date", "unknown")
        current_price_stored = holding.get("current_price", 0)
        pnl_pct = holding.get("unrealized_pnl_pct", 0)
        thesis = holding.get("thesis", "No thesis provided.")
        exit_condition = holding.get("exit_condition", "No exit condition set.")

        # Always fetch fresh live data
        live = fetch_live_data(ticker)
        company_name = live.get("company_name", ticker.replace(".NS", ""))

        # For MF proxy holdings, entry_price is the MF's average NAV per unit,
        # which is on a completely different scale from the proxy ETF's live price.
        # DO NOT recompute P&L from live price in that case — use stored unrealized_pnl_pct.
        is_mf_proxy = "proxy ETF" in thesis or "MF holding (proxy" in thesis
        current_price = live.get("current_price", current_price_stored) or current_price_stored
        if not is_mf_proxy and entry_price and current_price:
            pnl_pct = round(((current_price - entry_price) / entry_price) * 100, 1)
        # else: pnl_pct stays as stored from the MF statement — already correct

        news = fetch_stock_news(ticker, company_name, max_results=5)
        cached_ctx = self.stock_history.get_context_for_prompt(ticker)

        data_block = format_data_block(
            ticker=ticker,
            live=live,
            news=news,
            macro_summary=macro_chain.summary_for_prompt(),
            cached_context=cached_ctx,
        )

        # Add portfolio-specific context
        if is_mf_proxy:
            portfolio_block = (
                f"\n\n## PORTFOLIO CONTEXT\n"
                f"HOLDING TYPE: Mutual Fund — {ticker} is a proxy ETF used for technical "
                f"direction signals only. The ETF price above is NOT the investor's cost basis.\n"
                f"Actual MF P&L: {pnl_pct:+.1f}%  (from broker statement — authoritative)\n"
                f"Entry date: {entry_date}\n"
                f"Full context (actual invested vs current Rs. values): {thesis}\n"
                f"Exit condition: {exit_condition}\n"
            )
        else:
            portfolio_block = (
                f"\n\n## PORTFOLIO CONTEXT\n"
                f"Entry price:  Rs.{entry_price:,.2f}  (on {entry_date})\n"
                f"Current price: Rs.{current_price:,.2f}\n"
                f"Unrealized P&L: {pnl_pct:+.1f}%\n"
                f"Original thesis: {thesis}\n"
                f"Exit condition: {exit_condition}\n"
            )

        # Extract per-ticker previous recommendation if previous context is available
        prev_block = ""
        if previous_context and ticker in previous_context:
            lines = [l for l in previous_context.splitlines() if ticker in l]
            if lines:
                prev_block = (
                    f"\n\n## PREVIOUS RECOMMENDATION FOR {ticker}\n"
                    + "\n".join(lines) +
                    "\nConsider whether your view has changed since then and why."
                )

        user_msg = (
            data_block + portfolio_block + prev_block +
            "\n\nApply the mandatory thesis validation and blank-slate test. Return your action recommendation as JSON."
        )

        raw = self.llm.reason(
            system_prompt=_SYSTEM,
            user_message=user_msg,
            layer="layer2",
            max_tokens=2500,
        )

        # Save to stock history (shared with scout)
        story_dict = {
            "ticker": ticker,
            "company_name": company_name,
            "story": raw.get("narrative", ""),
            "conviction": "medium",
            "score": 50,
            "technicals_summary": raw.get("technicals_summary", ""),
            "fundamentals_summary": raw.get("fundamentals_summary", ""),
        }
        self.stock_history.save(ticker, story_dict)

        return HoldingAction(
            ticker=ticker,
            company_name=company_name,
            action=raw.get("action", "HOLD"),
            narrative=raw.get("narrative", "Analysis complete."),
            thesis_status=raw.get("thesis_status", "intact"),
            blank_slate_test=raw.get("blank_slate_test", "PASS"),
            blank_slate_note=raw.get("blank_slate_note", ""),
            macro_alignment=raw.get("macro_alignment", ""),
            technicals_summary=raw.get("technicals_summary", ""),
            fundamentals_summary=raw.get("fundamentals_summary", ""),
            exit_condition_status=raw.get("exit_condition_status", "not triggered"),
            entry_price=entry_price,
            current_price=current_price,
            pnl_pct=pnl_pct,
            key_risk=raw.get("key_risk", ""),
            reasoning_chain=raw.get("reasoning_chain", []),
            news_highlights=raw.get("news_highlights", []),
            recovery_scenario=raw.get("recovery_scenario", ""),
            upgrade_trigger=raw.get("upgrade_trigger", ""),
            downgrade_trigger=raw.get("downgrade_trigger", ""),
        )
