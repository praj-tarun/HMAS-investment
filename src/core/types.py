"""Core types and base classes for the HMAS agent system."""

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Any, Optional
from enum import Enum
import json


class SignalType(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Horizon(str, Enum):
    NEAR_TERM = "near-term"
    STRUCTURAL = "structural"


@dataclass
class SignalPacket:
    """
    Output from Layer 1 agents.

    signals: max 5 structured signal dicts (blueprint: signal packet, not prose)
    reasoning_chain: the agent's step-by-step COT — this is the explainability layer
    dominant_direction: agent's overall directional call
    india_relevance_filter_log: GeopoliticalAgent filter log (which events passed/failed filter)
    """
    agent_name: str
    timestamp: str
    signals: List[Dict[str, Any]] = field(default_factory=list)
    reasoning_chain: List[str] = field(default_factory=list)
    dominant_direction: str = "neutral"
    confidence: str = "medium"
    india_relevance_filter_log: Optional[List[Dict]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def add_signal(self, data_point: str, historical_context: str,
                   directional_implication: str, uncertainty: str, **kwargs):
        sig = {
            "data_point": data_point,
            "historical_context": historical_context,
            "directional_implication": directional_implication,
            "uncertainty": uncertainty,
        }
        sig.update(kwargs)
        self.signals.append(sig)


@dataclass
class Scorecard:
    """
    Output from Layer 2 Leads.

    dissent_appendix: written BEFORE main thesis (blueprint: anomaly is often alpha)
    reasoning_chain: the Lead's step-by-step synthesis COT
    For QuantLead: alignment_scores + key_divergences instead of a thesis
    """
    lead_name: str
    direction: SignalType
    confidence: Confidence
    horizon: Horizon
    thesis: str
    dissent_flags: List[str] = field(default_factory=list)
    dissent_appendix: Optional[Dict[str, Any]] = None
    reasoning_chain: List[str] = field(default_factory=list)
    escalation_flag: Optional[bool] = None
    escalation_reason: Optional[str] = None
    # QuantLead fields
    alignment_scores: Optional[Dict[str, Any]] = None
    key_divergences: Optional[List[str]] = None
    calibration_context: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_name": self.lead_name,
            "direction": self.direction.value,
            "confidence": self.confidence.value,
            "horizon": self.horizon.value,
            "thesis": self.thesis,
            "dissent_flags": self.dissent_flags,
            "dissent_appendix": self.dissent_appendix,
            "reasoning_chain": self.reasoning_chain,
            "escalation_flag": self.escalation_flag,
            "escalation_reason": self.escalation_reason,
            "alignment_scores": self.alignment_scores,
            "key_divergences": self.key_divergences,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class DecisionBrief:
    """
    Output from Chief Orchestrator — final decision per holding.

    reasoning_chain: the five-step COT per holding (anti-recency → thesis →
                     blank slate → conflict resolution → decision)
    thesis_validation_note: specific cross-reference to original Holdings Log thesis
    blank_slate_notes: if FAIL, must name sunk cost bias explicitly with P&L figure
    """
    ticker: str
    thesis_status: str        # Intact / Weakening / Broken
    technical_alignment: str  # Aligned / Diverging / Conflicted / Neutral
    flag: str                 # HOLD / WATCH / EXIT_CONDITION_APPROACHING
    reason: str               # One sentence — single most important driver
    blank_slate_test: str     # PASS / FAIL
    blank_slate_notes: Optional[str] = None
    thesis_validation_note: str = ""
    reasoning_chain: List[str] = field(default_factory=list)
    narrative: str = ""       # Human-readable analyst-style explanation (2–4 sentences)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def to_string(self) -> str:
        lines = [
            f"TICKER: {self.ticker}",
            f"Thesis status: {self.thesis_status}",
            f"Technical alignment: {self.technical_alignment}",
            f"Flag: {self.flag}",
            f"Reason: {self.reason}",
            f"Blank slate test: {self.blank_slate_test}",
        ]
        if self.blank_slate_notes:
            lines.append(f"  {self.blank_slate_notes}")
        return "\n".join(lines)


@dataclass
class BuyBrief:
    """
    Output from Chief Orchestrator — buy opportunity assessment for a watchlist ticker.

    flag: BUY_NOW / WAIT_FOR_ENTRY / AVOID
    buy_condition: specific trigger that must occur before acting (e.g., "RSI < 40 + earnings beat")
    entry_zone: price range considered attractive (e.g., "₹2,400–2,450")
    stop_loss: price level that invalidates the setup
    time_horizon: expected holding period if the setup triggers
    """
    ticker: str
    flag: str                   # BUY_NOW / WAIT_FOR_ENTRY / AVOID
    setup: str                  # One-sentence description of the opportunity
    buy_condition: str          # Specific trigger required before acting
    entry_zone: str             # Attractive price range
    stop_loss: str              # Invalidation level
    time_horizon: str           # Expected holding period
    conviction: str             # high / medium / low
    fundamental_quality: str    # Strong / Average / Weak
    valuation_status: str       # Cheap / Fair / Expensive
    macro_alignment: str        # Aligned / Neutral / Against
    reasoning_chain: List[str] = field(default_factory=list)
    narrative: str = ""         # Human-readable explanation with conditional buy/avoid logic

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def to_string(self) -> str:
        lines = [
            f"TICKER: {self.ticker}  [{self.flag}]",
            f"Setup: {self.setup}",
            f"Buy condition: {self.buy_condition}",
            f"Entry zone: {self.entry_zone}  |  Stop loss: {self.stop_loss}",
            f"Time horizon: {self.time_horizon}  |  Conviction: {self.conviction}",
            f"Fundamentals: {self.fundamental_quality}  |  Valuation: {self.valuation_status}  |  Macro: {self.macro_alignment}",
        ]
        return "\n".join(lines)


@dataclass
class GeneralMarketBrief:
    """
    Output when running in general market mode (no portfolio context).
    Provides a clean market read for any investor considering Indian equities.
    """
    macro_direction: str
    macro_confidence: str
    macro_horizon: str
    macro_thesis: str
    macro_key_risks: List[str] = field(default_factory=list)
    macro_dissent: Optional[str] = None
    micro_direction: str = "neutral"
    micro_thesis: str = ""
    sector_signals: List[Dict[str, Any]] = field(default_factory=list)
    commodity_brent_impact: str = ""
    commodity_gold_signal: str = ""
    flight_to_safety_active: bool = False
    week_in_review: str = ""
    top_risks: List[str] = field(default_factory=list)
    reasoning_chains: Dict[str, List[str]] = field(default_factory=dict)
    # Proactive opportunity suggestions — stocks/ETFs to buy or watch this week
    weekly_opportunities: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseAgent:
    def __init__(self, name: str):
        self.name = name

    def execute(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError(f"{self.name} must implement execute()")


class Layer1Agent(BaseAgent):
    def execute(self, **kwargs) -> SignalPacket:
        raise NotImplementedError(f"{self.name} must implement execute()")


class Layer2Lead(BaseAgent):
    def execute(self, **kwargs) -> Scorecard:
        raise NotImplementedError(f"{self.name} must implement execute()")


class ChiefOrchestrator(BaseAgent):
    def execute(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError(f"{self.name} must implement execute()")


# ─────────────────────────────────────────────────────────────────────────────
# v2 Types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MacroChainOutput:
    """
    Output from MacroChainAgent (Phase 1).

    causal_chain:   Plain-English step-by-step chain, e.g.
                    "crude $88 → OPEC restraint → India CAD widens → rupee pressure →
                     RBI on hold → PE compression → IT exporters benefit"
    causal_steps:   Structured list of {cause, effect, confidence}
    market_regime:  "risk-on" | "risk-off" | "mixed" | "sector-rotation"
    explore_themes: Sectors/assets to focus research on (e.g. ["IT", "Gold", "Pharma"])
    avoid_themes:   Sectors to skip (e.g. ["Banking", "Real Estate"])
    india_overlay:  Dict with rupee_outlook, rbi_stance, fii_sentiment, pe_impact
    """
    causal_chain: str
    causal_steps: List[Dict[str, Any]]
    market_regime: str
    regime_confidence: str
    explore_themes: List[str]
    avoid_themes: List[str]
    india_overlay: Dict[str, str]
    reasoning_chain: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary_for_prompt(self) -> str:
        """Compact string for injecting into research agent prompts."""
        themes_str = ", ".join(self.explore_themes) if self.explore_themes else "none identified"
        avoid_str = ", ".join(self.avoid_themes) if self.avoid_themes else "none"
        overlay = self.india_overlay or {}
        return (
            f"Macro regime: {self.market_regime.upper()} ({self.regime_confidence} confidence)\n"
            f"Causal chain: {self.causal_chain}\n"
            f"Explore themes: {themes_str}\n"
            f"Avoid themes: {avoid_str}\n"
            f"India overlay: rupee={overlay.get('rupee_outlook','?')} | "
            f"RBI={overlay.get('rbi_stance','?')} | "
            f"FII={overlay.get('fii_sentiment','?')} | "
            f"PE impact={overlay.get('pe_impact','?')}"
        )


@dataclass
class StockStory:
    """
    Output from StockResearchAgent (Phase 3) — the full investment case for one ticker.

    story:         Human-readable analyst-style narrative (3-5 sentences)
    score:         0-100 composite score (macro alignment 30% + fundamentals 25% + technicals 25% + quant 20%)
    from_cache:    True if this analysis was reused from the 7-day cache
    """
    ticker: str
    company_name: str
    story: str
    opportunity_type: str      # "macro_tailwind" | "value_play" | "momentum" | "defensive" | "avoid"
    entry_zone: str
    stop_loss: str
    time_horizon: str
    conviction: str            # "high" | "medium" | "low"
    score: float               # 0-100
    key_risk: str
    macro_alignment: str       # How this stock relates to the current macro regime
    technicals_summary: str    # RSI, MACD, MA position in one line
    fundamentals_summary: str  # PE, PB, ROE, earnings trend in one line
    news_highlights: List[str] = field(default_factory=list)
    reasoning_chain: List[str] = field(default_factory=list)
    from_cache: bool = False
    source_urls: List[str] = field(default_factory=list)   # Where it was found (verification)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HoldingAction:
    """
    Output from HoldingResearchAgent (Phase 3, Portfolio mode).

    Extends StockStory with portfolio-specific context.
    action: "HOLD" | "ADD" | "TRIM" | "EXIT"
    """
    ticker: str
    company_name: str
    action: str                # HOLD | ADD | TRIM | EXIT
    narrative: str             # Human-readable explanation with reasoning
    thesis_status: str         # "intact" | "weakening" | "broken"
    blank_slate_test: str      # "PASS" | "FAIL"
    blank_slate_note: str      # If FAIL: must name sunk cost bias + P&L
    macro_alignment: str
    technicals_summary: str
    fundamentals_summary: str
    exit_condition_status: str  # "not triggered" | "approaching" | "triggered"
    entry_price: float
    current_price: float
    pnl_pct: float
    key_risk: str
    reasoning_chain: List[str] = field(default_factory=list)
    news_highlights: List[str] = field(default_factory=list)
    from_cache: bool = False
    recovery_scenario: str = ""   # How far from breakeven, conditions for recovery
    upgrade_trigger: str = ""     # What would make agent recommend ADD
    downgrade_trigger: str = ""   # What would make agent recommend EXIT

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
