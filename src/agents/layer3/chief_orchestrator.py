"""
Chief Orchestrator — Layer 3.

Uses OpenAI o3-mini with the REACT (Reasoning and Acting) framework.
Produces DecisionBrief per holding (portfolio mode) or GeneralMarketBrief (general mode).

REACT Framework:
- REASONING PHASE: Analyze market conditions, evaluate evidence, form hypotheses
- ACTING PHASE: Determine specific investment actions based on reasoning
"""

from datetime import datetime
from typing import Dict, Any, Optional, List

from src.core.types import (
    ChiefOrchestrator, DecisionBrief, GeneralMarketBrief, BuyBrief,
    Scorecard, SignalPacket,
)
from src.core.llm_client import LLMClient
from src.memory.memory_mcp import MemoryMCP


_ORCHESTRATOR_SYSTEM = """
You are the Chief Orchestrator in HMAS (Hierarchical Multi-Agent Investment System).

You operate using the REACT (Reasoning and Acting) framework:
- REASONING PHASE: Analyze all inputs, evaluate evidence, form hypotheses about market conditions and portfolio positions
- ACTING PHASE: Based on your reasoning, determine specific investment actions and recommendations

You receive the complete synthesized view from all 3 layers and produce the final decision brief.
This is where the FINAL REASONING lives. Use the most thorough reasoning possible.

INPUTS (in this order of priority):
1. Portfolio context (holdings, theses, P&L, decision history, invalidated theses)
2. Macro Lead scorecard + dissent flags
3. Micro Lead scorecard + escalation flags
4. Quant Lead calibration modifier

REACT FRAMEWORK — FOLLOW THIS STRUCTURE EXACTLY FOR EVERY HOLDING:

=== REASONING PHASE ===

STEP 1 — SITUATION ANALYSIS:
Gather and synthesize all available information about the current market environment.
- What is the macro regime? (bullish/bearish/neutral)
- What is the micro environment? (sector rotations, domestic conditions)
- What technical signals are present?
- What is the risk environment? (volatility, flight-to-safety indicators)

STEP 2 — EVIDENCE EVALUATION:
Cross-reference current signals against historical patterns and portfolio context.
- Anti-recency check: What has been consistently true over 12 months vs. last 30 days?
- Thesis validation: Is the original reason for owning each holding still valid?
- Risk assessment: What are the key uncertainties and downside risks?

STEP 3 — HYPOTHESIS FORMATION:
Form clear hypotheses about what should happen next.
- What is the most likely scenario for each holding?
- What would cause the thesis to break?
- What triggers would improve or worsen the outlook?

=== ACTING PHASE ===

STEP 4 — DECISION DETERMINATION:
Based on reasoning above, determine the appropriate action for each holding.
- Blank slate test: Would you initiate this position today with current data?
- Conflict resolution: If signals conflict, which takes precedence and why?
- Flag assignment: HOLD / WATCH / EXIT_CONDITION_APPROACHING

STEP 5 — ACTION SPECIFICATION:
Define exactly what the investor should do and why.
- What specific conditions would trigger a change in recommendation?
- What are the key monitoring points?
- What is the time horizon for this decision?

SYSTEM BOUNDARY:
You produce a defensible, well-reasoned recommendation.
The final investment decision belongs to the investor. Frame your output accordingly.

PORTFOLIO MODE OUTPUT: Valid JSON only:
{
  "reasoning_phase": {
    "situation_analysis": "synthesis of current market environment",
    "evidence_evaluation": "cross-reference against history and context",
    "hypothesis_formation": "clear hypotheses about what should happen next"
  },
  "acting_phase": {
    "decision_determination": "action rationale based on reasoning",
    "action_specification": "specific recommendations and triggers"
  },
  "anti_recency_check": "one to two sentences: what has been true 12 months vs last 30 days",
  "decision_briefs": [
    {
      "ticker": "string",
      "thesis_status": "Intact | Weakening | Broken",
      "thesis_validation_note": "specific cross-reference to the Holdings Log thesis text — what confirms or challenges it",
      "technical_alignment": "Aligned | Diverging | Conflicted | Neutral",
      "flag": "HOLD | WATCH | EXIT_CONDITION_APPROACHING",
      "reason": "one sentence — the single most important driver of this flag",
      "blank_slate_test": "PASS | FAIL",
      "blank_slate_note": "if PASS: why thesis stands on current merits. If FAIL: MUST include 'sunk cost bias', P&L%, and 'fresh buyer would not initiate'.",
      "narrative": "Write 3–5 sentences as a thoughtful senior analyst explaining this holding to the investor. NOT bullet points — flowing prose. Include: (1) what is actually happening with this stock right now, (2) what is working for or against the original thesis, (3) what specific event or trigger would change the picture. Write as if you are talking to the investor directly. Example tone: 'HDFC Bank has been consolidating for 6 weeks after its Q3 miss, and the technical picture is actually starting to look constructive again — RSI has reset to 48 from an overbought 72. Your thesis of credit cycle recovery is still intact, but there's a test coming: if the March RBI meeting hints at a rate cut delay, BFSI sector rotation could weigh on it another 5%. I'd hold the position but tighten your mental stop to the Q3 low at ₹1,580.'",
      "reasoning_chain": [
        "REASONING — Situation Analysis: [market environment synthesis]",
        "REASONING — Evidence Evaluation: [historical cross-reference]",
        "REASONING — Hypothesis Formation: [what should happen next]",
        "ACTING — Decision Determination: [action rationale]",
        "ACTING — Action Specification: [specific recommendations]"
      ]
    }
  ]
}
"""

_WATCHLIST_SCAN_SYSTEM = """
You are the Chief Orchestrator in HMAS running in WATCHLIST SCAN MODE.

You operate using the REACT (Reasoning and Acting) framework:
- REASONING PHASE: Analyze market conditions, evaluate opportunities, assess risks
- ACTING PHASE: Determine specific buy/avoid/wait actions with clear triggers

You are given a list of tickers the investor is monitoring for potential buy opportunities.
For each watchlist ticker, produce a BuyBrief — a specific, actionable buy opportunity assessment.

Your job is NOT to say "watch more" or "do more research." Your job is to make a clear call:
  BUY_NOW: The setup is active NOW. All conditions are met. Entry is justified today.
  WAIT_FOR_ENTRY: The setup is valid but a specific trigger has not yet fired. Name the trigger.
  AVOID: The setup has broken down or fundamental/macro conditions are unfavorable.

REACT FRAMEWORK — FOR EACH WATCHLIST TICKER:

=== REASONING PHASE ===

Step 1 — OPPORTUNITY ANALYSIS:
Evaluate the fundamental quality and market positioning of each ticker.
- What is the fundamental profile? (valuation, quality, growth prospects)
- What is the technical setup? (momentum, support/resistance levels)
- How does macro environment impact this opportunity?

Step 2 — RISK ASSESSMENT:
Identify key risks and uncertainties for each potential investment.
- What could go wrong with this setup?
- What macro events could derail the opportunity?
- What technical levels would invalidate the trade?

Step 3 — PROBABILITY EVALUATION:
Assess the likelihood of success and timing considerations.
- What is the conviction level for this opportunity?
- What specific conditions need to be met?
- What is the optimal time horizon?

=== ACTING PHASE ===

Step 4 — ACTION DETERMINATION:
Based on reasoning above, determine the appropriate action.
- BUY_NOW: Setup active + conditions met + timing right
- WAIT_FOR_ENTRY: Valid setup + specific trigger needed
- AVOID: Setup broken + risks outweigh opportunities

Step 5 — EXECUTION SPECIFICATION:
Define exact parameters for the recommended action.
- Entry zones and stop losses
- Specific buy conditions and time horizons
- Key monitoring points and exit triggers

WATCHLIST SCAN OUTPUT: Valid JSON only:
{
  "reasoning_phase": {
    "market_environment": "synthesis of current macro/micro conditions",
    "risk_assessment": "key market risks and uncertainties",
    "opportunity_evaluation": "assessment of available setups"
  },
  "acting_phase": {
    "action_determination": "rationale for buy/wait/avoid decisions",
    "execution_specification": "specific parameters and triggers"
  },
  "anti_recency_check": "one to two sentences on what the macro regime has been vs this week's change",
  "buy_briefs": [
    {
      "ticker": "string",
      "flag": "BUY_NOW | WAIT_FOR_ENTRY | AVOID",
      "setup": "one sentence describing the opportunity or reason to avoid",
      "buy_condition": "specific trigger required, or 'All conditions met — act now' for BUY_NOW, or 'N/A' for AVOID",
      "entry_zone": "specific price range or N/A",
      "stop_loss": "specific price level with brief reason, or N/A",
      "time_horizon": "e.g. '2–3 weeks' or 'through earnings on [date]', or N/A",
      "conviction": "high | medium | low",
      "fundamental_quality": "Strong | Average | Weak",
      "valuation_status": "Cheap | Fair | Expensive | Unknown",
      "macro_alignment": "Aligned | Neutral | Against",
      "narrative": "Write 3–5 sentences as a real analyst speaking directly to the investor. Explain WHY this setup is or isn't interesting right now — reference the specific macro events, technicals, and fundamentals that matter. Give the conditional logic clearly: 'Buy if X happens, but avoid if Y happens.' Do not be vague. If you are saying AVOID, explain what specifically went wrong with the setup. If BUY_NOW, explain why the moment is right. Example: 'Infosys has pulled back 11% from its 52-week high after a cautious commentary in Q3 results, and RSI has washed out to 36 — the kind of reset that historically precedes a bounce in quality IT names. The fundamental picture remains strong: ROE above 30%, no debt, and analyst consensus is still buy. The trigger I am watching is the TCS earnings call this Thursday — if TCS management gives a positive FY26 guidance, IT sentiment will flip quickly and INFY becomes an immediate buy at ₹1,420–1,450. However if TCS cuts guidance, skip INFY entirely for another 2 weeks.'",
      "reasoning_chain": [
        "REASONING — Opportunity Analysis: [fundamental and technical evaluation]",
        "REASONING — Risk Assessment: [key risks and uncertainties]",
        "REASONING — Probability Evaluation: [conviction and timing]",
        "ACTING — Action Determination: [buy/wait/avoid rationale]",
        "ACTING — Execution Specification: [specific parameters]"
      ]
    }
  ]
}
"""

_GENERAL_MARKET_SYSTEM = """
You are the Chief Orchestrator in HMAS running in GENERAL MARKET MODE.

You operate using the REACT (Reasoning and Acting) framework:
- REASONING PHASE: Analyze market environment, identify opportunities and risks
- ACTING PHASE: Recommend specific investment actions with clear triggers and parameters

No portfolio context. Two goals:
  1. Give a clean market read on the current environment.
  2. Identify 3–5 specific stocks, ETFs, or instruments worth buying or watching this week —
     with conditional triggers written in plain English.

TONE: Write like a thoughtful senior portfolio manager briefing a retail investor on Sunday morning.
Not a data table. Real sentences. Real reasoning. If something is risky, say so plainly.
If a trade requires a specific event to play out, name the event and the price level.

For the weekly opportunities:
  - Include Indian equities (NSE-listed), Gold ETF, Index ETF, or sector ETFs if relevant.
  - For each opportunity, write a 3–4 sentence narrative that explains:
    (a) WHY this is interesting right now — the specific setup or theme driving it
    (b) WHAT has to happen for the trade to work (buy trigger)
    (c) WHAT would invalidate it (avoid trigger or red flag)
    (d) WHERE to enter and where to cut losses if wrong
  - Conviction: high (act now or very close), medium (watch and wait), low (bookmark only)
  - Recommendation: BUY_NOW / WATCH_CLOSELY / AVOID_THIS_WEEK / MONITOR_FOR_LATER

IMPORTANT: Do NOT list opportunities just to fill space. If only 2 setups are genuinely interesting
this week, list 2. Better to say "only 2 good setups visible this week" than to pad with weak ideas.

REACT FRAMEWORK FOR GENERAL MARKET ANALYSIS:

=== REASONING PHASE ===

Step 1 — ENVIRONMENT ANALYSIS:
Synthesize the current macro and micro market environment.
- What is the dominant macro theme? (growth, inflation, geopolitics)
- What is the domestic market sentiment? (FII flows, sector rotation)
- What are the key risks and uncertainties?

Step 2 — OPPORTUNITY IDENTIFICATION:
Scan for actionable investment opportunities across asset classes.
- Which sectors or themes show compelling risk-reward?
- What technical or fundamental setups are present?
- What event-driven opportunities exist?

Step 3 — RISK EVALUATION:
Assess the broader market risks and position sizing implications.
- What could derail the market this week?
- What is the risk environment? (volatility, correlations)
- What position sizing is appropriate?

=== ACTING PHASE ===

Step 4 — RECOMMENDATION FORMULATION:
Based on reasoning above, formulate specific investment recommendations.
- Which opportunities warrant action this week?
- What are the appropriate conviction levels?
- What triggers should investors watch?

Step 5 — EXECUTION GUIDANCE:
Provide specific parameters for each recommended action.
- Entry levels and stop losses
- Time horizons and monitoring points
- Risk management guidelines

OUTPUT: Valid JSON only:
{
  "reasoning_phase": {
    "environment_analysis": "synthesis of macro/micro market conditions",
    "opportunity_identification": "key investment opportunities identified",
    "risk_evaluation": "assessment of market risks and uncertainties"
  },
  "acting_phase": {
    "recommendation_formulation": "rationale for specific investment actions",
    "execution_guidance": "parameters and triggers for recommended trades"
  },
  "anti_recency_check": "one to two sentences on what has changed this week vs the month-long trend",
  "general_market_brief": {
    "macro_direction": "bullish | bearish | neutral",
    "macro_confidence": "high | medium | low",
    "macro_horizon": "near-term | structural",
    "macro_thesis": "2–3 sentence synthesis of the macro environment",
    "macro_key_risks": ["risk1", "risk2", "risk3"],
    "macro_dissent": "the most important counter-signal or anomaly, or null",
    "micro_direction": "bullish | bearish | neutral",
    "micro_thesis": "1–2 sentences on India domestic conditions and which sectors are in focus",
    "sector_signals": [
      {
        "sector": "string",
        "direction": "Bullish | Bearish | Neutral",
        "key_signal": "one sentence on what is driving this sector this week"
      }
    ],
    "commodity_brent_impact": "India implication of current crude level in plain language",
    "commodity_gold_signal": "what gold price action is signaling this week",
    "flight_to_safety_active": false,
    "week_in_review": "2–3 sentences written to an investor asking 'what happened this week and should I be worried?'",
    "top_risks": ["risk1 — why it matters", "risk2 — why it matters", "risk3 — why it matters"]
  },
  "weekly_opportunities": [
    {
      "ticker": "e.g. GOLDBEES.NS or HDFCBANK.NS or NIFTYBEES.NS",
      "name": "human-readable name, e.g. 'Gold ETF (GOLDBEES)' or 'HDFC Bank'",
      "asset_type": "Stock | Index ETF | Sector ETF | Gold ETF | Bond ETF",
      "recommendation": "BUY_NOW | WATCH_CLOSELY | AVOID_THIS_WEEK | MONITOR_FOR_LATER",
      "conviction": "high | medium | low",
      "narrative": "Write 3–4 sentences as a real analyst. Example: 'Gold has quietly moved up 4% in the last 10 days on the back of dollar weakness and persistent safe-haven demand. Technically it broke out above a 3-month resistance level. The key event this week is the US CPI print on Wednesday — if inflation comes in below 3.2%, the Fed pivot narrative strengthens and gold could run another 3-5%. I would buy GOLDBEES around ₹5,820–5,850 and keep a stop at ₹5,700 (below the breakout level). If CPI surprises to the upside, skip it for now.'",
      "buy_trigger": "specific condition that must occur — e.g. 'US CPI < 3.2% on Wednesday' or 'RSI breaks below 35 and holds'",
      "avoid_trigger": "specific condition that would invalidate the trade — e.g. 'US CPI > 3.5%' or 'Brent crosses $95'",
      "entry_zone": "price range, e.g. '₹5,820–5,850 for GOLDBEES.NS'",
      "stop_loss": "specific level with brief reason, e.g. '₹5,700 — below breakout support'",
      "time_horizon": "e.g. '1–2 weeks', '3–4 weeks', 'hold through earnings'",
      "key_risk": "single biggest risk to this trade in one sentence"
    }
  ]
}
"""
{
  "anti_recency_check": "one to two sentences on what has changed this week vs the month-long trend",
  "general_market_brief": {
    "macro_direction": "bullish | bearish | neutral",
    "macro_confidence": "high | medium | low",
    "macro_horizon": "near-term | structural",
    "macro_thesis": "2–3 sentence synthesis of the macro environment",
    "macro_key_risks": ["risk1", "risk2", "risk3"],
    "macro_dissent": "the most important counter-signal or anomaly, or null",
    "micro_direction": "bullish | bearish | neutral",
    "micro_thesis": "1–2 sentences on India domestic conditions and which sectors are in focus",
    "sector_signals": [
      {
        "sector": "string",
        "direction": "Bullish | Bearish | Neutral",
        "key_signal": "one sentence on what is driving this sector this week"
      }
    ],
    "commodity_brent_impact": "India implication of current crude level in plain language",
    "commodity_gold_signal": "what gold price action is signaling this week",
    "flight_to_safety_active": false,
    "week_in_review": "2–3 sentences written to an investor asking 'what happened this week and should I be worried?'",
    "top_risks": ["risk1 — why it matters", "risk2 — why it matters", "risk3 — why it matters"]
  },
  "weekly_opportunities": [
    {
      "ticker": "e.g. GOLDBEES.NS or HDFCBANK.NS or NIFTYBEES.NS",
      "name": "human-readable name, e.g. 'Gold ETF (GOLDBEES)' or 'HDFC Bank'",
      "asset_type": "Stock | Index ETF | Sector ETF | Gold ETF | Bond ETF",
      "recommendation": "BUY_NOW | WATCH_CLOSELY | AVOID_THIS_WEEK | MONITOR_FOR_LATER",
      "conviction": "high | medium | low",
      "narrative": "Write 3–4 sentences as a real analyst. Example: 'Gold has quietly moved up 4% in the last 10 days on the back of dollar weakness and persistent safe-haven demand. Technically it broke out above a 3-month resistance level. The key event this week is the US CPI print on Wednesday — if inflation comes in below 3.2%, the Fed pivot narrative strengthens and gold could run another 3-5%. I would buy GOLDBEES around ₹5,820–5,850 and keep a stop at ₹5,700 (below the breakout level). If CPI surprises to the upside, skip it for now.'",
      "buy_trigger": "specific condition that must occur — e.g. 'US CPI < 3.2% on Wednesday' or 'RSI breaks below 35 and holds'",
      "avoid_trigger": "specific condition that would invalidate the trade — e.g. 'US CPI > 3.5%' or 'Brent crosses $95'",
      "entry_zone": "price range, e.g. '₹5,820–5,850 for GOLDBEES.NS'",
      "stop_loss": "specific level with brief reason, e.g. '₹5,700 — below breakout support'",
      "time_horizon": "e.g. '1–2 weeks', '3–4 weeks', 'hold through earnings'",
      "key_risk": "single biggest risk to this trade in one sentence"
    }
  ]
}
"""


class HMASChiefOrchestrator(ChiefOrchestrator):

    def __init__(self, memory: MemoryMCP, llm: LLMClient):
        super().__init__("Chief Orchestrator")
        self.memory = memory
        self.llm = llm

    def execute(
        self,
        portfolio_context: Optional[Dict[str, Any]] = None,
        macro_lead_scorecard: Optional[Scorecard] = None,
        micro_lead_scorecard: Optional[Scorecard] = None,
        quant_lead_scorecard: Optional[Scorecard] = None,
        fundamentals_packet: Optional[SignalPacket] = None,
        mode: str = "portfolio",
        watchlist_tickers: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Returns dict with:
          - 'briefs': List[DecisionBrief] (portfolio mode)
          - 'buy_briefs': List[BuyBrief] (scan mode)
          - 'general_market_brief': GeneralMarketBrief (general mode)
          - 'anti_recency_check': str
        """
        if mode == "scan":
            return self._run_watchlist_scan(
                watchlist_tickers or [],
                macro_lead_scorecard,
                micro_lead_scorecard,
                quant_lead_scorecard,
                fundamentals_packet,
            )
        if mode == "general":
            return self._run_general_market(
                macro_lead_scorecard, micro_lead_scorecard, portfolio_context
            )
        return self._run_portfolio(
            portfolio_context, macro_lead_scorecard, micro_lead_scorecard,
            quant_lead_scorecard, fundamentals_packet,
        )

    # ── Portfolio Mode ────────────────────────────────────────────────────────

    def _run_portfolio(
        self,
        portfolio_context: Optional[Dict],
        macro: Optional[Scorecard],
        micro: Optional[Scorecard],
        quant: Optional[Scorecard],
        fundamentals: Optional[SignalPacket] = None,
    ) -> Dict[str, Any]:
        user_msg = self._build_portfolio_prompt(portfolio_context, macro, micro, quant, fundamentals)
        raw = self.llm.reason(
            system_prompt=_ORCHESTRATOR_SYSTEM,
            user_message=user_msg,
            layer="layer3",
            max_tokens=3000,
        )

        anti_recency = raw.get("anti_recency_check", "")
        reasoning_phase = raw.get("reasoning_phase", {})
        acting_phase = raw.get("acting_phase", {})
        
        briefs = []
        for b in raw.get("decision_briefs", []):
            brief = DecisionBrief(
                ticker=b.get("ticker", "UNKNOWN"),
                thesis_status=b.get("thesis_status", "Intact"),
                technical_alignment=b.get("technical_alignment", "Neutral"),
                flag=b.get("flag", "HOLD").upper(),
                reason=b.get("reason", ""),
                blank_slate_test=b.get("blank_slate_test", "PASS").upper(),
                blank_slate_notes=b.get("blank_slate_note"),
                thesis_validation_note=b.get("thesis_validation_note", ""),
                reasoning_chain=b.get("reasoning_chain", []),
                narrative=b.get("narrative", ""),
            )
            briefs.append(brief)

        return {
            "anti_recency_check": anti_recency,
            "reasoning_phase": reasoning_phase,
            "acting_phase": acting_phase,
            "briefs": briefs,
            "buy_briefs": [],
            "general_market_brief": None,
        }

    def _build_portfolio_prompt(
        self,
        portfolio_context: Optional[Dict],
        macro: Optional[Scorecard],
        micro: Optional[Scorecard],
        quant: Optional[Scorecard],
        fundamentals: Optional[SignalPacket] = None,
    ) -> str:
        sections = []

        # Portfolio context
        if portfolio_context:
            holdings = portfolio_context.get("current_holdings", [])
            if holdings:
                h_lines = [
                    f"  {h['ticker']}:\n"
                    f"    Entry: ₹{h['entry_price']} | Current: ₹{h['current_price']} | P&L: {h['unrealized_pnl_pct']:+.1f}%\n"
                    f"    Original thesis: {h['thesis']}\n"
                    f"    Exit condition: {h['exit_condition']}"
                    for h in holdings
                ]
                sections.append("## PORTFOLIO HOLDINGS LOG\n" + "\n".join(h_lines))

            recent_decisions = portfolio_context.get("recent_decisions", [])
            if recent_decisions:
                d_lines = [
                    f"  {d['date']}: {d['system_recommendation']} → {d['action_taken']}"
                    + (f" | Outcome: {d.get('outcome_30d', 'pending')}" if d.get("outcome_30d") else "")
                    for d in recent_decisions
                ]
                sections.append("## RECENT DECISIONS (12-month context)\n" + "\n".join(d_lines))
            else:
                sections.append("## RECENT DECISIONS\nNo prior decisions logged.")

            invalidated = portfolio_context.get("invalidated_theses", [])
            if invalidated:
                inv_lines = [
                    f"  ⚠ {it['ticker']}: {it['invalidation_reason']} (invalidated {it['date_invalidated']})"
                    for it in invalidated
                ]
                sections.append("## INVALIDATED THESES — REQUIRES IMMEDIATE FLAG\n" + "\n".join(inv_lines))

            sections.append(f"## PORTFOLIO STATE\n  {portfolio_context.get('drawdown_context', '')}")

        # Macro Lead
        if macro:
            dissent_text = ""
            if macro.dissent_appendix:
                da = macro.dissent_appendix
                dissent_text = f"\n  Dissent: {da.get('dissent_summary', '')} (significance: {da.get('anomaly_significance', 'Unknown')})"
            sections.append(
                f"## MACRO LEAD SCORECARD\n"
                f"  Direction: {macro.direction.value.upper()} | Confidence: {macro.confidence.value} | Horizon: {macro.horizon.value}\n"
                f"  Thesis: {macro.thesis}"
                + dissent_text
                + (f"\n  ⚠ PRIORITY ESCALATION: {macro.escalation_reason}" if macro.escalation_flag else "")
            )

        # Micro Lead
        if micro:
            sections.append(
                f"## MICRO LEAD SCORECARD\n"
                f"  Direction: {micro.direction.value.upper()} | Confidence: {micro.confidence.value} | Horizon: {micro.horizon.value}\n"
                f"  Thesis: {micro.thesis}"
                + (f"\n  ⚠ ESCALATION FLAG: {micro.escalation_reason}" if micro.escalation_flag else "")
            )

        # Quant Lead
        if quant and quant.alignment_scores:
            align_lines = [
                f"  {ticker}: {scores.get('alignment', 'Neutral')}"
                + (f" — {scores.get('divergence_note', '')}" if scores.get("divergence_note") else "")
                for ticker, scores in quant.alignment_scores.items()
            ]
            sections.append(
                f"## QUANT LEAD CALIBRATION\n"
                f"  Context: {quant.calibration_context or quant.thesis}\n"
                + "\n".join(align_lines)
                + ("\n  KEY DIVERGENCES: " + "; ".join(quant.key_divergences) if quant.key_divergences else "")
            )

        # Fundamentals Agent signals
        if fundamentals and fundamentals.signals:
            fund_lines = []
            for sig in fundamentals.signals:
                ticker = sig.get("ticker", "")
                verdict = sig.get("fundamental_verdict", "NEUTRAL")
                valuation = sig.get("valuation", "Unknown")
                quality = sig.get("quality", "Unknown")
                growth = sig.get("growth", "Unknown")
                upside = sig.get("analyst_upside_pct")
                upside_str = f" | Analyst upside: {upside:+.1f}%" if upside is not None else ""
                fund_lines.append(
                    f"  {ticker}: {verdict} — Valuation: {valuation} | Quality: {quality} | Growth: {growth}{upside_str}"
                )
            if fund_lines:
                sections.append("## FUNDAMENTALS AGENT SIGNALS\n" + "\n".join(fund_lines))

        sections.append(
            "\nFor each holding, follow the 5-step COT. Name sunk cost bias explicitly if blank slate fails. Return JSON."
        )
        return "\n\n".join(sections)

    # ── Watchlist Scan Mode ───────────────────────────────────────────────────

    def _run_watchlist_scan(
        self,
        watchlist_tickers: List[str],
        macro: Optional[Scorecard],
        micro: Optional[Scorecard],
        quant: Optional[Scorecard],
        fundamentals: Optional[SignalPacket],
    ) -> Dict[str, Any]:
        if not watchlist_tickers:
            return {
                "anti_recency_check": "",
                "briefs": [],
                "buy_briefs": [],
                "general_market_brief": None,
            }

        user_msg = self._build_watchlist_prompt(watchlist_tickers, macro, micro, quant, fundamentals)
        raw = self.llm.reason(
            system_prompt=_WATCHLIST_SCAN_SYSTEM,
            user_message=user_msg,
            layer="layer3",
            max_tokens=3000,
        )

        anti_recency = raw.get("anti_recency_check", "")
        reasoning_phase = raw.get("reasoning_phase", {})
        acting_phase = raw.get("acting_phase", {})
        
        buy_briefs = []
        for b in raw.get("buy_briefs", []):
            brief = BuyBrief(
                ticker=b.get("ticker", "UNKNOWN"),
                flag=b.get("flag", "WAIT_FOR_ENTRY").upper(),
                setup=b.get("setup", ""),
                buy_condition=b.get("buy_condition", ""),
                entry_zone=b.get("entry_zone", "N/A"),
                stop_loss=b.get("stop_loss", "N/A"),
                time_horizon=b.get("time_horizon", "N/A"),
                conviction=b.get("conviction", "low").lower(),
                fundamental_quality=b.get("fundamental_quality", "Unknown"),
                valuation_status=b.get("valuation_status", "Unknown"),
                macro_alignment=b.get("macro_alignment", "Neutral"),
                reasoning_chain=b.get("reasoning_chain", []),
                narrative=b.get("narrative", ""),
            )
            buy_briefs.append(brief)

        return {
            "anti_recency_check": anti_recency,
            "reasoning_phase": reasoning_phase,
            "acting_phase": acting_phase,
            "briefs": [],
            "buy_briefs": buy_briefs,
            "general_market_brief": None,
        }

    def _build_watchlist_prompt(
        self,
        watchlist_tickers: List[str],
        macro: Optional[Scorecard],
        micro: Optional[Scorecard],
        quant: Optional[Scorecard],
        fundamentals: Optional[SignalPacket],
    ) -> str:
        sections = []
        sections.append(
            "## WATCHLIST TICKERS TO SCAN\n"
            + ", ".join(watchlist_tickers)
            + "\nFor each ticker, produce a BuyBrief with specific actionable parameters."
        )

        # Macro Lead
        if macro:
            da = macro.dissent_appendix or {}
            sections.append(
                f"## MACRO LEAD\n"
                f"  Direction: {macro.direction.value.upper()} | Confidence: {macro.confidence.value} | Horizon: {macro.horizon.value}\n"
                f"  Thesis: {macro.thesis}\n"
                f"  Dissent: {da.get('dissent_summary', 'None')}"
                + (f"\n  ⚠ ESCALATION: {macro.escalation_reason}" if macro.escalation_flag else "")
            )

        # Micro Lead
        if micro:
            sections.append(
                f"## MICRO LEAD\n"
                f"  Direction: {micro.direction.value.upper()} | Confidence: {micro.confidence.value}\n"
                f"  Thesis: {micro.thesis}"
                + (f"\n  ⚠ ESCALATION: {micro.escalation_reason}" if micro.escalation_flag else "")
            )

        # Quant Lead
        if quant and quant.alignment_scores:
            align_lines = [
                f"  {ticker}: {scores.get('alignment', 'Neutral')}"
                + (f" — {scores.get('divergence_note', '')}" if scores.get("divergence_note") else "")
                for ticker, scores in quant.alignment_scores.items()
                if ticker in watchlist_tickers
            ]
            if align_lines:
                sections.append(
                    f"## QUANT TECHNICALS (watchlist tickers)\n"
                    + "\n".join(align_lines)
                )

        # Fundamentals
        if fundamentals and fundamentals.signals:
            fund_lines = []
            for sig in fundamentals.signals:
                if sig.get("ticker") in watchlist_tickers:
                    ticker = sig.get("ticker", "")
                    verdict = sig.get("fundamental_verdict", "NEUTRAL")
                    valuation = sig.get("valuation", "Unknown")
                    quality = sig.get("quality", "Unknown")
                    growth = sig.get("growth", "Unknown")
                    upside = sig.get("analyst_upside_pct")
                    upside_str = f" | Analyst upside: {upside:+.1f}%" if upside is not None else ""
                    fund_lines.append(
                        f"  {ticker}: {verdict} — Valuation: {valuation} | Quality: {quality} | Growth: {growth}{upside_str}"
                    )
            if fund_lines:
                sections.append("## FUNDAMENTALS AGENT (watchlist tickers)\n" + "\n".join(fund_lines))

        sections.append(
            "\nFor each watchlist ticker, follow the 5-step COT. Be specific with entry zones, stop losses, and conditions. Return JSON."
        )
        return "\n\n".join(sections)

    # ── General Market Mode ───────────────────────────────────────────────────

    def _run_general_market(
        self,
        macro: Optional[Scorecard],
        micro: Optional[Scorecard],
        portfolio_context: Optional[Dict],
    ) -> Dict[str, Any]:
        user_msg = self._build_general_prompt(macro, micro)
        raw = self.llm.reason(
            system_prompt=_GENERAL_MARKET_SYSTEM,
            user_message=user_msg,
            layer="layer3",
            max_tokens=2048,
        )

        anti_recency = raw.get("anti_recency_check", "")
        reasoning_phase = raw.get("reasoning_phase", {})
        acting_phase = raw.get("acting_phase", {})
        
        gm_raw = raw.get("general_market_brief", raw)

        brief = GeneralMarketBrief(
            macro_direction=gm_raw.get("macro_direction", "neutral"),
            macro_confidence=gm_raw.get("macro_confidence", "medium"),
            macro_horizon=gm_raw.get("macro_horizon", "near-term"),
            macro_thesis=gm_raw.get("macro_thesis", ""),
            macro_key_risks=gm_raw.get("macro_key_risks", []),
            macro_dissent=gm_raw.get("macro_dissent"),
            micro_direction=gm_raw.get("micro_direction", "neutral"),
            micro_thesis=gm_raw.get("micro_thesis", ""),
            sector_signals=gm_raw.get("sector_signals", []),
            commodity_brent_impact=gm_raw.get("commodity_brent_impact", ""),
            commodity_gold_signal=gm_raw.get("commodity_gold_signal", ""),
            flight_to_safety_active=gm_raw.get("flight_to_safety_active", False),
            week_in_review=gm_raw.get("week_in_review", ""),
            top_risks=gm_raw.get("top_risks", []),
            weekly_opportunities=raw.get("weekly_opportunities", []),
        )

        return {
            "anti_recency_check": anti_recency,
            "reasoning_phase": reasoning_phase,
            "acting_phase": acting_phase,
            "briefs": [],
            "general_market_brief": brief,
        }

    def _build_general_prompt(self, macro: Optional[Scorecard], micro: Optional[Scorecard]) -> str:
        sections = []

        if macro:
            da = macro.dissent_appendix or {}
            sections.append(
                f"## MACRO LEAD\n"
                f"  Direction: {macro.direction.value.upper()} | Confidence: {macro.confidence.value} | Horizon: {macro.horizon.value}\n"
                f"  Thesis: {macro.thesis}\n"
                f"  Dissent: {da.get('dissent_summary', macro.dissent_flags[0] if macro.dissent_flags else 'None')}\n"
                f"  Macro Reasoning Chain:\n"
                + "\n".join(f"    {s}" for s in macro.reasoning_chain)
            )

        if micro:
            sections.append(
                f"## MICRO LEAD\n"
                f"  Direction: {micro.direction.value.upper()} | Confidence: {micro.confidence.value} | Horizon: {micro.horizon.value}\n"
                f"  Thesis: {micro.thesis}\n"
                f"  Micro Reasoning Chain:\n"
                + "\n".join(f"    {s}" for s in micro.reasoning_chain)
            )

        sections.append("\nSynthesize all signals into a general market brief for an investor considering Indian equities. Return JSON.")
        return "\n\n".join(sections)
