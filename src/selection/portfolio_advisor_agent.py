"""
PortfolioAdvisorAgent — Phase 4 (Portfolio mode).

Receives all holding actions from Phase 3 plus the macro chain context.
Produces:
  - Final confirmed action per holding (with potential overrides from portfolio-level view)
  - Macro overlay — which holdings benefit / are at risk from current regime
  - Concentration analysis — correlated downside risk across holdings
  - Scout cross-reference — if scout found something that complements the portfolio
  - Anti-sunk-cost summary — calls out all FAIL blank-slate tests prominently

Model: o3-mini (layer3) for final portfolio reasoning.
"""

from typing import List, Dict, Any, Optional

from src.core.llm_client import LLMClient
from src.core.types import HoldingAction, MacroChainOutput

_SYSTEM = """
You are the PortfolioAdvisorAgent in HMAS v2. You are a senior portfolio manager
conducting a practical, forward-looking review of a retail investor's holdings.

INVESTOR CONTEXT (always assume this unless told otherwise):
- Long-term retail investor, holding for 1+ years
- Cannot time the market precisely — needs clear, specific triggers, not "sell everything now"
- Risk-off phases are TEMPORARY — distinguishing cyclical downturns from structural breaks is critical
- Exiting equity at the bottom of a drawdown often destroys value — consider this before recommending EXIT
- Locking in a -12% loss to move to cash is only justified if the structural thesis is broken

You receive individual holding reports (action, recovery scenario, upgrade/downgrade triggers)
plus the macro regime and scout opportunities.

YOUR DELIVERABLES — all must be specific and actionable:

A. PER-HOLDING CONFIRMED ACTIONS
   For each holding provide:
   - Confirmed action (HOLD / ADD / TRIM / HOLD_WATCH / EXIT)
   - The BEST MOVE NOW: one specific, concrete action the investor should take this week
   - Recovery path: how much gain needed to break even, and what conditions unlock that
   - Specific upgrade trigger: exact condition to add more (price level, macro signal, technical)
   - Specific downgrade trigger: exact condition to exit (price level, macro break, time stop)
   Never say "monitor closely" — give a price or event.

B. GOLD PROFIT-TAKING ANALYSIS
   GOLDBEES.NS is a hedge that has performed well. Evaluate:
   - Is it overweight relative to the equity drawdown?
   - Would trimming gold (at current highs) and redeploying into equity dips improve the portfolio?
   - Give a specific recommendation: "Trim X% of GOLDBEES if price exceeds Rs.Y, redeploy into Z"

C. REBALANCING PLAN (if applicable)
   If the portfolio is unbalanced, give a specific rebalancing suggestion:
   - Which position to reduce and by how much
   - Where to redeploy the proceeds
   - Timing guidance (now, or wait for a specific trigger)

D. CONCENTRATION RISK
   Multiple holdings exposed to same macro factor? Name the factor, tickers, correlated risk,
   and what single event would hit all of them simultaneously.

E. WHAT TO DO IN THE NEXT 30 DAYS
   A short, practical checklist of 3-5 actions the investor should take (or watch for).
   Format: "IF [condition] THEN [action]" for each item.

TONE: Act like a trusted advisor, not a risk-compliance bot.
"Risk-off environment hurts equities" is an observation, not advice.
"Hold MIDSMALL — you need 14% recovery to break even. That likely comes when FII outflows
stabilise post-US tariff resolution (watch USD/INR below 84). Set a stop at [X]." — that is advice.

OUTPUT: Valid JSON only:
{
  "holdings_actions": [
    {
      "ticker": "TICKER.NS",
      "confirmed_action": "HOLD | ADD | TRIM | HOLD_WATCH | EXIT",
      "best_move_now": "one specific concrete action this week",
      "narrative": "3-4 sentence reasoning: current position, why this action, what changes the view",
      "recovery_path": "X% needed to break even; unlocked by [specific macro/technical condition]",
      "upgrade_trigger": "specific condition to add more",
      "downgrade_trigger": "specific condition to exit",
      "macro_overlay": "benefits | hurts | neutral — cyclical or structural, and why it matters",
      "blank_slate_test": "PASS | FAIL",
      "pnl_pct": -11.9
    }
  ],
  "gold_profit_taking": {
    "recommendation": "HOLD_FULL | TRIM_PARTIAL | TRIM_SIGNIFICANT",
    "reasoning": "specific reasoning on gold weight vs equity drawdown",
    "specific_action": "e.g. Trim 25% of GOLDBEES if it exceeds Rs.125, redeploy into MIDSMALL on dip"
  },
  "rebalancing_plan": "specific rebalancing recommendation or 'Portfolio is reasonably balanced'",
  "concentration_risks": [
    {
      "factor": "equity market risk",
      "exposed_tickers": ["MIDSMALL.NS", "JUNIORBEES.NS", "INFRABEES.NS"],
      "risk": "single event that hits all simultaneously and what that looks like"
    }
  ],
  "next_30_days_checklist": [
    "IF [FII outflows > Rs.5000cr this week] THEN [do not add to equity positions yet]",
    "IF [USD/INR stabilises below 84] THEN [begin SIP into MIDSMALL]",
    "IF [GOLDBEES.NS crosses Rs.125] THEN [trim 25% and hold cash for equity dip]"
  ],
  "portfolio_level_advice": "3-4 sentence overall posture: what the portfolio looks like now, best overall move",
  "sunk_cost_summary": {
    "fail_count": 2,
    "affected_tickers": ["MIDSMALL.NS"],
    "note": "acknowledge but distinguish: is this cyclical (hold through) or structural (exit)?"
  },
  "reasoning_chain": [
    "Step 1 — Individual holding review and recovery math: ...",
    "Step 2 — Gold weight and profit-taking opportunity: ...",
    "Step 3 — Rebalancing and capital allocation: ...",
    "Step 4 — Concentration risk and single-event scenarios: ...",
    "Step 5 — 30-day action checklist: ..."
  ]
}
"""


def _format_holding_actions(actions: List[HoldingAction]) -> str:
    lines = ["## HOLDING RESEARCH REPORTS\n"]
    for a in actions:
        pnl_str = f"{a.pnl_pct:+.1f}%" if a.pnl_pct else "N/A"
        bst = f"Blank-slate: {a.blank_slate_test}"
        if a.blank_slate_test == "FAIL" and a.blank_slate_note:
            bst += f" — {a.blank_slate_note[:120]}"
        lines.append(
            f"### {a.ticker} ({a.company_name})\n"
            f"Recommended action: {a.action}  |  Thesis: {a.thesis_status}  |  {bst}\n"
            f"P&L: {pnl_str}\n"
            f"Narrative: {a.narrative}\n"
            f"Recovery scenario: {a.recovery_scenario}\n"
            f"Upgrade trigger: {a.upgrade_trigger}\n"
            f"Downgrade trigger: {a.downgrade_trigger}\n"
            f"Macro alignment: {a.macro_alignment}\n"
            f"Technicals: {a.technicals_summary}\n"
            f"Fundamentals: {a.fundamentals_summary}\n"
            f"Exit condition status: {a.exit_condition_status}\n"
            f"Key risk: {a.key_risk}\n"
        )
    return "\n".join(lines)


def _format_scout_top5(scout_results: Optional[Dict]) -> str:
    if not scout_results or not scout_results.get("top5"):
        return "## SCOUT TOP 5\nScout not run this session."
    lines = ["## SCOUT TOP 5 (this week's best opportunities)"]
    for item in scout_results["top5"]:
        lines.append(
            f"  {item.get('rank','?')}. {item.get('ticker','')}  [{item.get('recommendation','')}]  "
            f"conviction={item.get('conviction','')}  score={item.get('final_score','?')}\n"
            f"     {item.get('story','')[:150]}"
        )
    return "\n".join(lines)


class PortfolioAdvisorAgent:

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def run(
        self,
        holding_actions: List[HoldingAction],
        macro_chain: MacroChainOutput,
        scout_results: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Produce a final portfolio-level recommendation package.

        Args:
            holding_actions: List of HoldingAction from Phase 3
            macro_chain:     MacroChainOutput from Phase 1
            scout_results:   Optional top-5 from ScoutSelectionAgent for cross-referencing
        """
        if not holding_actions:
            return {
                "holdings_actions": [],
                "portfolio_level_advice": "Portfolio is empty. Run 'python run.py add TICKER.NS' to add holdings.",
                "reasoning_chain": [],
            }

        holdings_block = _format_holding_actions(holding_actions)
        scout_block = _format_scout_top5(scout_results)

        user_msg = (
            f"## MACRO CONTEXT\n{macro_chain.summary_for_prompt()}\n\n"
            + holdings_block + "\n\n"
            + scout_block +
            "\n\nReview all holdings. Produce confirmed actions, macro overlay, "
            "concentration analysis, and portfolio advice. Return JSON."
        )

        raw = self.llm.reason(
            system_prompt=_SYSTEM,
            user_message=user_msg,
            layer="layer3",
            max_tokens=5000,
        )

        return {
            "holdings_actions": raw.get("holdings_actions", []),
            "gold_profit_taking": raw.get("gold_profit_taking", {}),
            "rebalancing_plan": raw.get("rebalancing_plan", ""),
            "concentration_risks": raw.get("concentration_risks", []),
            "next_30_days_checklist": raw.get("next_30_days_checklist", []),
            "scout_crossref": raw.get("scout_crossref", {}),
            "sunk_cost_summary": raw.get("sunk_cost_summary", {}),
            "portfolio_level_advice": raw.get("portfolio_level_advice", ""),
            "reasoning_chain": raw.get("reasoning_chain", []),
        }
