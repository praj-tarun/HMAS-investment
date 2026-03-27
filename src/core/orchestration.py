"""State management and trigger evaluation for the HMAS workflow."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from src.core.types import SignalPacket, Scorecard, DecisionBrief


@dataclass
class HMASState:
    """State object for the HMAS LangGraph."""

    # Portfolio context (always first)
    portfolio_context: Dict[str, Any] = field(default_factory=dict)

    # Layer 1 agent outputs (signal packets)
    india_business_signals: Optional[SignalPacket] = None
    geopolitical_signals: Optional[SignalPacket] = None
    commodity_signals: Optional[SignalPacket] = None
    sector_signals: Optional[SignalPacket] = None
    quant_signals: Optional[SignalPacket] = None
    fundamentals_signals: Optional[SignalPacket] = None
    portfolio_context_agent_output: Optional[Dict[str, Any]] = None

    # Layer 2 lead outputs (all Scorecards; QuantLead uses alignment_scores field)
    macro_lead_scorecard: Optional[Scorecard] = None
    micro_lead_scorecard: Optional[Scorecard] = None
    quant_lead_modifier: Optional[Scorecard] = None

    # Flags and escalations
    dissent_flags: List[str] = field(default_factory=list)
    priority_escalations: List[Dict[str, Any]] = field(default_factory=list)

    # Activation triggers
    active_triggers: List[str] = field(default_factory=list)

    # Final output
    decision_briefs: List[DecisionBrief] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for LangGraph."""
        return {
            "portfolio_context": self.portfolio_context,
            "india_business_signals": self.india_business_signals.to_dict() if self.india_business_signals else None,
            "geopolitical_signals": self.geopolitical_signals.to_dict() if self.geopolitical_signals else None,
            "commodity_signals": self.commodity_signals.to_dict() if self.commodity_signals else None,
            "sector_signals": self.sector_signals.to_dict() if self.sector_signals else None,
            "quant_signals": self.quant_signals.to_dict() if self.quant_signals else None,
            "portfolio_context_agent_output": self.portfolio_context_agent_output,
            "macro_lead_scorecard": self.macro_lead_scorecard.to_dict() if self.macro_lead_scorecard else None,
            "micro_lead_scorecard": self.micro_lead_scorecard.to_dict() if self.micro_lead_scorecard else None,
            "quant_lead_modifier": self.quant_lead_modifier.to_dict() if self.quant_lead_modifier else None,
            "dissent_flags": self.dissent_flags,
            "priority_escalations": self.priority_escalations,
            "active_triggers": self.active_triggers,
            "decision_briefs": [b.to_dict() for b in self.decision_briefs],
        }


class TriggerEvaluator:
    """Evaluates which agents should be activated based on triggers."""

    @staticmethod
    def evaluate_triggers(trigger_events: List[str]) -> set:
        """
        Evaluate triggers and return set of agents to activate.

        Args:
            trigger_events: List of trigger names from conditional activation table

        Returns:
            Set of agent names to activate
        """
        trigger_activations = {
            "scheduled_weekly_review": {
                "agents": [
                    "india_business",
                    "geopolitical",
                    "commodity",
                    "sector",
                    "quant",
                    "portfolio_context",
                ],
                "leads": ["macro_lead", "micro_lead", "quant_lead"],
            },
            "rbi_fed_announcement": {
                "agents": ["geopolitical", "commodity"],
                "leads": ["macro_lead"],
            },
            "holding_move_3pct": {
                "agents": ["quant"],
                "leads": ["quant_lead"],
            },
            "geopolitical_event": {
                "agents": ["geopolitical"],
                "leads": ["macro_lead"],
            },
            "manual_flag_holding": {
                "agents": ["india_business", "quant"],
            },
            "commodity_spike": {
                "agents": ["commodity"],
                "leads": ["macro_lead"],
            },
        }

        active_agents = set()
        for trigger in trigger_events:
            activation = trigger_activations.get(trigger, {})
            active_agents.update(activation.get("agents", []))
            active_agents.update(activation.get("leads", []))

        return active_agents
