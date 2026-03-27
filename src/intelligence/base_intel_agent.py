"""
BaseIntelAgent — abstract base for all 4 Phase-0 intelligence agents.

Each subclass:
  1. Calls _load_history() to get historical context for its prompt
  2. Gathers raw data (news, prices, macro indicators)
  3. Calls LLM to produce a structured analysis
  4. Calls _save_history() to persist the result
  5. Returns a dict compatible with MacroChainAgent input
"""

from abc import abstractmethod
from typing import Dict, Any, List
from datetime import datetime

from src.core.llm_client import LLMClient
from src.history.intel_history import IntelHistory


class BaseIntelAgent:
    """Abstract base class for Phase-0 intelligence agents."""

    def __init__(self, name: str, history_key: str, window_days: int, llm: LLMClient):
        self.name = name
        self.llm = llm
        self.history = IntelHistory(history_key, window_days=window_days)

    def run(self) -> Dict[str, Any]:
        """
        Execute the agent. Template method:
          1. Gather raw data
          2. Build prompt with historical context injected
          3. Call LLM
          4. Parse output
          5. Save to history
          6. Return structured packet
        """
        print(f"  [Intel] {self.name}...")
        try:
            raw_data = self._gather_data()
            history_ctx = self.history.context_for_prompt()
            prompt_data = self._build_prompt(raw_data, history_ctx)
            llm_result = self.llm.reason(
                system_prompt=prompt_data["system"],
                user_message=prompt_data["user"],
                layer="layer1",
                max_tokens=1500,
            )
            packet = self._parse_result(llm_result, raw_data)
            self._persist_to_history(packet)
            packet["agent"] = self.name
            packet["timestamp"] = datetime.now().isoformat()
            packet["history_trend"] = self.history.trend_summary
            print(f"      -> {self.name}: {packet.get('regime','?')} | {packet.get('confidence','?')}")
            return packet
        except Exception as exc:
            print(f"  [WARN] {self.name} failed: {exc}")
            return {
                "agent": self.name,
                "timestamp": datetime.now().isoformat(),
                "regime": "unknown",
                "confidence": "low",
                "summary": f"Agent failed: {exc}",
                "key_signals": [],
                "reasoning_chain": [f"ERROR: {exc}"],
                "history_trend": self.history.trend_summary,
            }

    @abstractmethod
    def _gather_data(self) -> Dict[str, Any]:
        """Fetch raw data for this agent. Returns a dict of raw inputs."""

    @abstractmethod
    def _build_prompt(self, raw_data: Dict[str, Any], history_ctx: str) -> Dict[str, str]:
        """Return {'system': ..., 'user': ...} for the LLM call."""

    @abstractmethod
    def _parse_result(self, llm_result: Dict[str, Any], raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse LLM JSON output into a standardised packet dict."""

    def _persist_to_history(self, packet: Dict[str, Any]) -> None:
        """Save today's result to the rolling history file."""
        self.history.append(
            summary=packet.get("summary", ""),
            key_signals=packet.get("key_signals", []),
            regime=packet.get("regime", "unknown"),
        )
