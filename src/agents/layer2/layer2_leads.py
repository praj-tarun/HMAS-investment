"""
Layer 2 Leads — Domain leads that synthesize Layer 1 signals via LLM reasoning.

Each lead:
- Has a system prompt encoding the exact COT from the blueprint
- Formats Layer 1 signal packets as structured input
- Calls OpenAI gpt-4o for synthesis
- Maps the response to a Scorecard
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from src.core.types import (
    Scorecard, Confidence, SignalType, Horizon, Layer2Lead, SignalPacket,
)
from src.core.llm_client import LLMClient


def _normalize_direction(val: str) -> SignalType:
    v = (val or "neutral").lower().strip()
    if "bullish" in v or v == "bull":
        return SignalType.BULLISH
    if "bearish" in v or v == "bear":
        return SignalType.BEARISH
    return SignalType.NEUTRAL


def _normalize_confidence(val: str) -> Confidence:
    v = (val or "medium").lower().strip()
    if v == "high":
        return Confidence.HIGH
    if v == "low":
        return Confidence.LOW
    return Confidence.MEDIUM


def _normalize_horizon(val: str) -> Horizon:
    v = (val or "near-term").lower().strip()
    if "struct" in v or "long" in v or "month" in v:
        return Horizon.STRUCTURAL
    return Horizon.NEAR_TERM


def _format_signal_packet(packet: Optional[SignalPacket], label: str) -> str:
    if not packet:
        return f"## {label}\nNo data available.\n"
    lines = [f"## {label} (Overall: {packet.dominant_direction.upper()}, Confidence: {packet.confidence})"]
    if packet.reasoning_chain:
        lines.append("Reasoning chain:")
        lines.extend(f"  {step}" for step in packet.reasoning_chain)
    if packet.signals:
        lines.append("Signals:")
        for i, s in enumerate(packet.signals, 1):
            dp = s.get("data_point", "")
            impl = s.get("directional_implication", "")
            india = s.get("india_impact", s.get("india_transmission_mechanism", ""))
            unc = s.get("uncertainty", "")
            lines.append(f"  [{i}] {dp}")
            if impl:
                lines.append(f"      Direction: {impl} | Uncertainty: {unc}")
            if india:
                lines.append(f"      India impact: {india}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Macro Lead
# ─────────────────────────────────────────────────────────────────────────────

_MACRO_LEAD_SYSTEM = """
You are the Macro Lead in HMAS (Hierarchical Multi-Agent Investment System).

CONSOLIDATES: Geopolitical Agent signals + Commodity Agent signals
YOUR JOB: Synthesize the global macro environment into a single scorecard for Indian equities.

CRITICAL STRUCTURAL RULE — DISSENT APPENDIX BEFORE THESIS:
Step 1 of your chain-of-thought is ALWAYS the dissent check.
Before you synthesize anything, ask:
  "What in the data does NOT fit the narrative I am about to tell?"
  "What is the anomaly, the outlier, the signal that breaks my dominant story?"
The dissent_appendix key in your JSON MUST appear BEFORE the scorecard key.
The anomaly is often where the alpha is. Writing it first prevents you from rationalizing it away.

CHAIN-OF-THOUGHT (in this order):
Step 1 — DISSENT CHECK (before synthesis):
  Read both signal packets. Do they point in the same direction? If not:
  - Are they contradicting on DIFFERENT time horizons? (e.g., near-term bearish FII, structural bullish macro)
    → These are COMPATIBLE. Describe the split.
  - Are they contradicting on the SAME time horizon about the SAME India equity outcome?
    → These are CONTRADICTORY. Flag for Priority Escalation.
Step 2 — Identify dominant narrative: what is the macro environment saying about India's equity risk premium?
Step 3 — India-specific translation:
  "What does this global macro mean for: (a) FII equity allocation to India, (b) rupee trajectory,
   (c) RBI policy room, (d) Indian equity multiples (P/E expansion or compression)?"
Step 4 — Synthesize scorecard, with confidence reflecting the dissent findings.
  If high-significance dissent exists → confidence cannot be "high".

OUTPUT: Valid JSON only, dissent_appendix MUST appear before scorecard:
{
  "dissent_appendix": {
    "dissent_items": [
      {
        "signal_source": "geopolitical | commodity",
        "signal_content": "what this signal says",
        "why_it_does_not_fit": "explicit contradiction with dominant narrative"
      }
    ],
    "anomaly_significance": "High | Medium | Low | None",
    "dissent_summary": "one sentence: what the anomaly is and why it matters"
  },
  "reasoning_chain": [
    "Step 1 — Dissent check: [findings — written before synthesis]",
    "Step 2 — Dominant narrative: [what both signals agree on]",
    "Step 3 — India risk premium translation: [FII/rupee/RBI/multiples]",
    "Step 4 — Synthesis: [how dissent affects confidence]"
  ],
  "scorecard": {
    "direction": "bullish | bearish | neutral",
    "confidence": "high | medium | low",
    "horizon": "near-term | structural",
    "thesis": "one to two sentence synthesis of the macro story for Indian equities",
    "dissent_flag": "the single most important contradicting signal, or null if none"
  }
}
"""


class MacroLead(Layer2Lead):

    SYSTEM_PROMPT = _MACRO_LEAD_SYSTEM

    def __init__(self, llm: LLMClient):
        super().__init__("Macro Lead")
        self.llm = llm

    def execute(
        self,
        geopolitical_signals: Optional[SignalPacket] = None,
        commodity_signals: Optional[SignalPacket] = None,
        mode: str = "portfolio",
        **kwargs,
    ) -> Scorecard:
        user_msg = self._build_user_message(geopolitical_signals, commodity_signals)
        raw = self.llm.reason(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_msg,
            layer="layer2",
            max_tokens=2048,
        )
        return self._to_scorecard(raw)

    def _build_user_message(self, geo: Optional[SignalPacket], commodity: Optional[SignalPacket]) -> str:
        sections = [
            _format_signal_packet(geo, "GEOPOLITICAL AGENT OUTPUT"),
            _format_signal_packet(commodity, "COMMODITY AGENT OUTPUT"),
            "\nWrite your dissent_appendix first, then your reasoning_chain, then your scorecard. Return JSON.",
        ]
        return "\n\n".join(sections)

    def _to_scorecard(self, raw: dict) -> Scorecard:
        sc_raw = raw.get("scorecard", raw)  # Fallback: some models may flatten the structure
        da_raw = raw.get("dissent_appendix", {})

        direction = _normalize_direction(sc_raw.get("direction", "neutral"))
        confidence = _normalize_confidence(sc_raw.get("confidence", "medium"))
        horizon = _normalize_horizon(sc_raw.get("horizon", "near-term"))
        thesis = sc_raw.get("thesis", "Macro signals analysed.")

        dissent_flag = sc_raw.get("dissent_flag")
        dissent_flags = [dissent_flag] if dissent_flag else []

        return Scorecard(
            lead_name=self.name,
            direction=direction,
            confidence=confidence,
            horizon=horizon,
            thesis=thesis,
            dissent_flags=dissent_flags,
            dissent_appendix=da_raw if da_raw else None,
            reasoning_chain=raw.get("reasoning_chain", []),
            escalation_flag=raw.get("priority_escalation", False),
            escalation_reason=raw.get("escalation_reason"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Micro Lead
# ─────────────────────────────────────────────────────────────────────────────

_MICRO_LEAD_SYSTEM = """
You are the Micro Lead in HMAS (Hierarchical Multi-Agent Investment System).

CONSOLIDATES: India Business Agent signals + Sector Agent signals
YOUR JOB: Synthesize the domestic micro environment for the specific holdings in this portfolio.

CONFLICT RESOLUTION CHAIN-OF-THOUGHT (follow this sequence exactly):

Step 1 — CAUSAL DIRECTIONALITY:
  Are conflicting signals operating on different time horizons or genuinely contradicting the same future?
  Example A: "RBI rate cut bullish for valuations over 12 months" + "rising oil bearish for margins in 3 months"
    → Different horizons. Conclusion: "near-term bearish / medium-term bullish" — SYNTHESIZE.
  Example B: "India Business Agent says Q4 earnings strong" + "Sector Agent says demand deteriorating"
    → Same time horizon, same reality. CONTRADICTORY → escalation_flag = true.

Step 2 — PORTFOLIO EXPOSURE MAPPING:
  Which signal has greater DIRECT sensitivity to the actual holdings?
  Name specific tickers. "Rising oil is a direct margin threat to RELIANCE's chemical segment"
  is portfolio-contextualized reasoning. "Macro risk" is not.
  The signal that hits actual held positions harder carries more weight.

Step 3 — ASYMMETRIC RISK WEIGHTING:
  Given capital-preservation posture, confirmed BEARISH signals carry 1.5x the weight of equivalent bullish signals.
  This is a hardcoded rule reflecting rational risk management — cost of wrong-downside > cost of missing upside.
  Show the arithmetic explicitly in your reasoning_chain:
    "India Business: 1 bullish signal, 1 bearish signal. Sector: 1 bearish signal.
     Weighted: bullish=1, bearish=(1+1)×1.5=3. Direction: bearish."

Step 4 — ESCALATE OR SYNTHESIZE?
  - Different time horizons with clear portfolio implications → SYNTHESIZE. Note the temporal split.
  - Genuinely contradictory about the SAME near-term outcome with high portfolio stakes
    → escalation_flag: true, escalation_reason: [what the contradiction is and why both must reach Orchestrator raw]

OUTPUT: Valid JSON only:
{
  "reasoning_chain": [
    "Step 1 — Causal directionality: [are signals on different horizons or genuinely contradictory?]",
    "Step 2 — Portfolio exposure mapping: [which signal hits actual holdings harder? Name tickers.]",
    "Step 3 — Asymmetric risk weighting: bullish=X, bearish=Y, weighted_bearish=Y×1.5, result: [direction]",
    "Step 4 — Decision: [synthesize or escalate, and why]"
  ],
  "scorecard": {
    "direction": "bullish | bearish | neutral",
    "confidence": "high | medium | low",
    "horizon": "near-term | structural",
    "thesis": "specific synthesis of India business and sector signals relative to held positions",
    "dissent_flag": "signal that doesn't fit the main narrative, or null",
    "escalation_flag": false,
    "escalation_reason": null
  }
}
"""


class MicroLead(Layer2Lead):

    SYSTEM_PROMPT = _MICRO_LEAD_SYSTEM

    def __init__(self, llm: LLMClient):
        super().__init__("Micro Lead")
        self.llm = llm

    def execute(
        self,
        india_business_signals: Optional[SignalPacket] = None,
        sector_signals: Optional[SignalPacket] = None,
        portfolio_context: Optional[Dict[str, Any]] = None,
        mode: str = "portfolio",
        **kwargs,
    ) -> Scorecard:
        user_msg = self._build_user_message(india_business_signals, sector_signals, portfolio_context, mode)
        raw = self.llm.reason(
            system_prompt=self.MICRO_LEAD_SYSTEM_with_mode(mode),
            user_message=user_msg,
            layer="layer2",
            max_tokens=2048,
        )
        return self._to_scorecard(raw)

    @staticmethod
    def MICRO_LEAD_SYSTEM_with_mode(mode: str) -> str:
        extra = ""
        if mode == "general":
            extra = "\nNOTE: Running in general market mode. No specific portfolio exposure mapping — skip Step 2 or apply to general India equity investor."
        return _MICRO_LEAD_SYSTEM + extra

    def _build_user_message(
        self,
        india_biz: Optional[SignalPacket],
        sector: Optional[SignalPacket],
        portfolio_context: Optional[Dict],
        mode: str,
    ) -> str:
        sections = [
            _format_signal_packet(india_biz, "INDIA BUSINESS AGENT OUTPUT"),
            _format_signal_packet(sector, "SECTOR AGENT OUTPUT"),
        ]

        if mode == "portfolio" and portfolio_context:
            holdings = portfolio_context.get("current_holdings", [])
            if holdings:
                h_lines = [
                    f"  {h['ticker']}: P&L {h['unrealized_pnl_pct']:+.1f}% | {h['thesis']}"
                    for h in holdings
                ]
                sections.append("## PORTFOLIO CONTEXT (for exposure mapping)\n" + "\n".join(h_lines))

            drawdown = portfolio_context.get("drawdown_context", "")
            if drawdown:
                sections.append(f"## DRAWDOWN CONTEXT\n  {drawdown}")

        sections.append(
            "\nFollow the 4-step conflict resolution COT. Show the asymmetric weighting arithmetic. Return JSON."
        )
        return "\n\n".join(sections)

    def _to_scorecard(self, raw: dict) -> Scorecard:
        sc_raw = raw.get("scorecard", raw)

        direction = _normalize_direction(sc_raw.get("direction", "neutral"))
        confidence = _normalize_confidence(sc_raw.get("confidence", "medium"))
        horizon = _normalize_horizon(sc_raw.get("horizon", "near-term"))
        thesis = sc_raw.get("thesis", "Micro signals analysed.")

        dissent_flag = sc_raw.get("dissent_flag")
        escalation = sc_raw.get("escalation_flag", False)
        escalation_reason = sc_raw.get("escalation_reason")

        return Scorecard(
            lead_name=self.name,
            direction=direction,
            confidence=confidence,
            horizon=horizon,
            thesis=thesis,
            dissent_flags=[dissent_flag] if dissent_flag else [],
            reasoning_chain=raw.get("reasoning_chain", []),
            escalation_flag=escalation,
            escalation_reason=escalation_reason,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Quant Lead
# ─────────────────────────────────────────────────────────────────────────────

_QUANT_LEAD_SYSTEM = """
You are the Quant Lead in HMAS (Hierarchical Multi-Agent Investment System).

YOUR ROLE: You are a CALIBRATION LAYER, not a third vote.
Your output is a modifier document attached to the Macro and Micro Lead reports.
You do NOT produce an independent thesis or a standalone recommendation.

YOUR ONE QUESTION: "What is the market price IMPLYING about the fundamental thesis
that the Macro and Micro Leads just presented?"

ALIGNMENT DEFINITIONS:
- ALIGNED: Technical posture confirms the fundamental direction.
    (Macro+Micro say Bullish + price in uptrend + MACD bullish = Aligned)
    (Macro+Micro say Bearish + price declining + MACD bearish = Aligned)
- DIVERGING: Technical moving against fundamentals without a strong signal.
    (Fundamentals neutral but price declining on bearish MACD = Diverging — price may be leading)
    (Fundamentals bullish but price range-bound = Diverging — market not yet confirming)
- CONFLICTED: Strong technical extreme DIRECTLY contradicts a clear fundamental call.
    (Fundamentals say Bullish strongly, but RSI >80 on declining volume = Conflicted)
    (Fundamentals say Bearish, but RSI <25 with high-delivery recovery = Conflicted)
- NEUTRAL: Technicals are flat and not informative either way.

DIVERGENCE NAMING IS YOUR PRIMARY FUNCTION:
If price is telling a different story than fundamentals, you MUST name it explicitly.
"Price forming a death cross on declining volume while fundamentals say neutral — market
may be leading the fundamental deterioration" is a valuable signal. Burying it is not acceptable.

CHAIN-OF-THOUGHT:
Step 1 — Read what Macro+Micro fundamentals are saying (direction, horizon, thesis).
Step 2 — For each holding: what is the technical reading?
Step 3 — Compare: "Fundamentals say X. Price says Y. Are these the same story?"
Step 4 — Assign alignment score. If Diverging or Conflicted, name the specific divergence.

OUTPUT: Valid JSON only:
{
  "calibration_context": "what Macro+Micro fundamentals are saying in one sentence",
  "reasoning_chain": [
    "TICKER: Fundamentals say [X]. Price says [Y via MACD/RSI/52w]. Assessment: [ALIGNED/DIVERGING/CONFLICTED].",
    ...
  ],
  "alignment_modifier": {
    "per_holding": [
      {
        "ticker": "string",
        "alignment": "Aligned | Diverging | Conflicted | Neutral",
        "technical_summary": "what price/momentum is saying",
        "fundamental_summary": "what macro/micro fundamentals say",
        "divergence_note": "null or SPECIFIC named divergence — this is the key signal"
      }
    ],
    "divergence_flags": ["named divergences to surface to Orchestrator"]
  },
  "dominant_direction": "aligned | mixed | diverging",
  "confidence": "high | medium | low"
}
"""


class QuantLead(Layer2Lead):

    SYSTEM_PROMPT = _QUANT_LEAD_SYSTEM

    def __init__(self, llm: LLMClient):
        super().__init__("Quant Lead")
        self.llm = llm

    def execute(
        self,
        quant_signals: Optional[SignalPacket] = None,
        macro_lead_scorecard: Optional[Scorecard] = None,
        micro_lead_scorecard: Optional[Scorecard] = None,
        portfolio_context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Scorecard:
        if not quant_signals or not quant_signals.signals:
            return Scorecard(
                lead_name=self.name,
                direction=SignalType.NEUTRAL,
                confidence=Confidence.LOW,
                horizon=Horizon.NEAR_TERM,
                thesis="No quant data available.",
                reasoning_chain=["Quant Lead skipped — no technical data provided."],
                alignment_scores={},
                key_divergences=[],
            )

        user_msg = self._build_user_message(quant_signals, macro_lead_scorecard, micro_lead_scorecard, portfolio_context)
        raw = self.llm.reason(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_msg,
            layer="layer2",
            max_tokens=2000,
        )
        return self._to_scorecard(raw)

    def _build_user_message(
        self,
        quant: Optional[SignalPacket],
        macro: Optional[Scorecard],
        micro: Optional[Scorecard],
        portfolio_context: Optional[Dict],
    ) -> str:
        sections = []

        # Fundamental context from Macro+Micro
        macro_summary = (
            f"Direction: {macro.direction.value.upper()}, Confidence: {macro.confidence.value}, "
            f"Horizon: {macro.horizon.value}\nThesis: {macro.thesis}"
        ) if macro else "No Macro Lead data."

        micro_summary = (
            f"Direction: {micro.direction.value.upper()}, Confidence: {micro.confidence.value}, "
            f"Horizon: {micro.horizon.value}\nThesis: {micro.thesis}"
        ) if micro else "No Micro Lead data."

        sections.append("## MACRO LEAD SCORECARD\n" + macro_summary)
        sections.append("## MICRO LEAD SCORECARD\n" + micro_summary)

        # Quant technical readings
        if quant and quant.signals:
            tech_lines = []
            for s in quant.signals:
                ticker = s.get("ticker", "UNKNOWN")
                tech_lines.append(
                    f"  {ticker}:\n"
                    f"    RSI: {s.get('rsi', 'N/A')} ({s.get('rsi_zone', '')})\n"
                    f"    MACD: {s.get('macd_signal', 'N/A')}"
                    + (" [FRESH CROSSOVER]" if s.get("fresh_crossover") else "") + "\n"
                    f"    52w: {s.get('price_52w_position', 'N/A')} ({s.get('price_52w_percentile', 'N/A')}th pct)\n"
                    f"    BB: {s.get('bb_position', 'N/A')}\n"
                    f"    Volume: {s.get('volume_note', 'N/A')}\n"
                    f"    Technical posture: {s.get('posture_detail', s.get('directional_implication', 'N/A'))}"
                )
            sections.append("## QUANT AGENT TECHNICAL READINGS\n" + "\n".join(tech_lines))
        else:
            sections.append("## QUANT DATA: No technical readings available.")

        sections.append(
            "\nFor each holding: compare fundamental direction vs technical posture. "
            "Name any divergences explicitly. Return calibration modifier as JSON."
        )
        return "\n\n".join(sections)

    def _to_scorecard(self, raw: dict) -> Scorecard:
        modifier = raw.get("alignment_modifier", {})
        per_holding = modifier.get("per_holding", [])
        divergence_flags = modifier.get("divergence_flags", [])

        # Build alignment_scores dict keyed by ticker
        alignment_scores = {
            item["ticker"]: {
                "alignment": item.get("alignment", "Neutral"),
                "technical_summary": item.get("technical_summary", ""),
                "fundamental_summary": item.get("fundamental_summary", ""),
                "divergence_note": item.get("divergence_note"),
            }
            for item in per_holding
            if item.get("ticker")
        }

        # Overall direction is just informational — Quant Lead is not a vote
        dominant = raw.get("dominant_direction", "mixed")
        direction = SignalType.NEUTRAL

        return Scorecard(
            lead_name=self.name,
            direction=direction,
            confidence=_normalize_confidence(raw.get("confidence", "medium")),
            horizon=Horizon.NEAR_TERM,
            thesis=raw.get("calibration_context", "Quant calibration complete."),
            reasoning_chain=raw.get("reasoning_chain", []),
            alignment_scores=alignment_scores,
            key_divergences=divergence_flags,
            calibration_context=raw.get("calibration_context"),
        )
