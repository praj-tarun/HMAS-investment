"""
MacroChainAgent — Phase 1.

Receives the 4 intelligence packets and produces:
  - An explicit causal chain in plain English
  - Market regime classification
  - explore_themes / avoid_themes for the universe screener
  - India-specific overlay

Uses gpt-4o (layer2) for complex multi-step causal reasoning.
Output is cached with a 2-hour TTL so scout + portfolio don't re-run it.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.core.llm_client import LLMClient
from src.core.types import MacroChainOutput

_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "intel_history" / "macro_chain_cache.json"
_CACHE_TTL_HOURS = 2

_SYSTEM = """
You are the MacroChainAgent in HMAS v2. You receive intelligence reports from 4 specialized
agents and synthesize them into a single, explicit economic causal chain for Indian equity markets.

YOUR PRIMARY OUTPUT: An explicit causal chain that traces macro inputs to India equity outcomes.

GOOD EXAMPLE:
"Brent crude sustained above $87 (3rd consecutive week above $85) → OPEC supply discipline
→ India import bill rises ~$1.5B/month → CAD widens to 2.1% of GDP → rupee under pressure
(USD/INR testing 85) → RBI cannot cut rates (CPI at 5.2%, above comfort zone) → bond yields
sticky at 7.1% → equity PE compression of 5-8% → rate-sensitive sectors (Banking, NBFC,
Real Estate) face headwinds; IT and Pharma exporters benefit from INR weakness (3-4% revenue
boost in rupee terms)."

BAD EXAMPLE: "Macro is uncertain. Markets are volatile." (too vague, no mechanism)

CHAIN RULES:
1. Every step must name a specific mechanism, not just a direction
2. Use actual numbers where data supports it (crude $87, not "high crude")
3. The chain must end with sector-level India equity implications
4. Identify WINNERS and LOSERS by sector name

THEME IDENTIFICATION:
From the chain, identify which sectors/assets are in tailwind (explore) vs headwind (avoid).
Be specific: "IT" not "technology". "Gold ETF" not "commodities".

INDIA OVERLAY: State explicitly:
- Rupee outlook and USD/INR range expectation
- RBI stance (cut / hold / hike risk)
- FII sentiment (net buyers / sellers / neutral)
- PE multiple direction (expanding / stable / compressing)

OUTPUT: Valid JSON only:
{
  "causal_chain": "single-paragraph causal chain from macro input to India sector outcomes",
  "causal_steps": [
    {"step": 1, "cause": "...", "effect": "...", "confidence": "high|medium|low"}
  ],
  "market_regime": "risk-on | risk-off | mixed | sector-rotation",
  "regime_confidence": "high | medium | low",
  "explore_themes": ["sector1", "sector2", "asset1"],
  "avoid_themes": ["sector3", "sector4"],
  "india_overlay": {
    "rupee_outlook": "one-line rupee direction and expected range",
    "rbi_stance": "cut-possible | on-hold | hike-risk",
    "fii_sentiment": "net-buyers | net-sellers | neutral | mixed",
    "pe_impact": "compressing | stable | expanding",
    "key_risk": "single most important risk to the base case"
  },
  "reasoning_chain": [
    "Step 1 — Synthesizing news intel: ...",
    "Step 2 — Global markets posture: ...",
    "Step 3 — Geopolitical transmission: ...",
    "Step 4 — Macro indicators: ...",
    "Step 5 — Causal chain construction: ...",
    "Step 6 — Theme and sector identification: ..."
  ]
}
"""


def _format_intel_packet(packet: Optional[Dict], label: str) -> str:
    if not packet:
        return f"## {label}\nNo data available.\n"
    lines = [
        f"## {label}",
        f"Regime: {packet.get('regime','?')} | Confidence: {packet.get('confidence','?')}",
        f"Summary: {packet.get('summary','')}",
        "Key signals:",
    ]
    for sig in packet.get("key_signals", [])[:5]:
        lines.append(f"  - {sig}")
    trend = packet.get("history_trend", "")
    if trend and trend != "No prior history available — first run.":
        lines.append(f"Multi-week trend: {trend}")
    return "\n".join(lines)


class MacroChainAgent:

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def run(
        self,
        news_packet: Optional[Dict] = None,
        global_markets_packet: Optional[Dict] = None,
        geopolitics_packet: Optional[Dict] = None,
        macro_data_packet: Optional[Dict] = None,
        previous_context: str = "",
    ) -> MacroChainOutput:
        """
        Synthesize 4 intel packets into a macro chain.
        Returns cached result if < TTL hours old.
        """
        cached = self._load_cache()
        if cached:
            print("  [MacroChain] Using cached macro chain (< 2h old)")
            return cached

        print("  [MacroChain] Building economic causal chain...")
        sections = [
            _format_intel_packet(news_packet, "NEWS INTELLIGENCE"),
            _format_intel_packet(global_markets_packet, "GLOBAL MARKETS"),
            _format_intel_packet(geopolitics_packet, "GEOPOLITICS"),
            _format_intel_packet(macro_data_packet, "MACRO DATA INDICATORS"),
        ]
        if previous_context:
            sections.append(
                f"## PREVIOUS SESSION CONTEXT\n{previous_context}\n"
                "Note what has changed since then — regime shift, new risks, thesis evolution."
            )
        sections.append(
            "\nSynthesize all inputs into a causal chain. Name explicit mechanisms and sectors. Return JSON."
        )
        user_msg = "\n\n".join(sections)

        raw = self.llm.reason(
            system_prompt=_SYSTEM,
            user_message=user_msg,
            layer="layer2",
            max_tokens=3000,
        )

        output = MacroChainOutput(
            causal_chain=raw.get("causal_chain", "Macro analysis complete."),
            causal_steps=raw.get("causal_steps", []),
            market_regime=raw.get("market_regime", "mixed"),
            regime_confidence=raw.get("regime_confidence", "medium"),
            explore_themes=raw.get("explore_themes", []),
            avoid_themes=raw.get("avoid_themes", []),
            india_overlay=raw.get("india_overlay", {}),
            reasoning_chain=raw.get("reasoning_chain", []),
            timestamp=datetime.now().isoformat(),
        )

        self._save_cache(output)
        print(f"      -> MacroChain: {output.market_regime} | explore={output.explore_themes}")
        return output

    def _load_cache(self) -> Optional[MacroChainOutput]:
        if not _CACHE_PATH.exists():
            return None
        try:
            with open(_CACHE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            ts = data.get("timestamp", "")
            if not ts:
                return None
            age = datetime.now() - datetime.fromisoformat(ts)
            if age > timedelta(hours=_CACHE_TTL_HOURS):
                return None
            return MacroChainOutput(**{k: v for k, v in data.items() if k in MacroChainOutput.__dataclass_fields__})
        except Exception:
            return None

    def _save_cache(self, output: MacroChainOutput) -> None:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(output.to_dict(), f, indent=2, ensure_ascii=False)
