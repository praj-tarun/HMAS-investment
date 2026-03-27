"""
HMAS main workflow — orchestrates all layers with trigger-based conditional activation.

Supports two modes:
  "portfolio" — full system with portfolio-specific guidance per holding
  "general"   — general India equity market read (no portfolio required)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from src.core.orchestration import HMASState, TriggerEvaluator
from src.core.llm_client import LLMClient
from src.core.types import DecisionBrief, GeneralMarketBrief, BuyBrief, Scorecard
from src.memory.memory_mcp import MemoryMCP
from src.mcp_tools.mcp_tools import (
    india_news_mcp, world_news_mcp, market_mcp, quant_mcp, macro_mcp, fundamental_mcp,
)
from src.agents.layer1.layer1_agents import (
    PortfolioContextAgent, IndiaBusinessAgent, GeopoliticalAgent,
    CommodityAgent, SectorAgent, QuantAgent, FundamentalsAgent,
)
from src.agents.layer2.layer2_leads import MacroLead, MicroLead, QuantLead
from src.agents.layer3.chief_orchestrator import HMASChiefOrchestrator


# ── Scout universe ────────────────────────────────────────────────────────────
# Loaded from scout_universe.txt (project root) — edit that file to add/remove tickers.
# Falls back to built-in defaults if the file is missing.

_SCOUT_UNIVERSE_DEFAULTS = [
    "HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS", "SBIN.NS",
    "TCS.NS", "INFY.NS", "HCLTECH.NS",
    "RELIANCE.NS", "ONGC.NS",
    "ITC.NS", "HINDUNILVR.NS",
    "MARUTI.NS", "TATAMOTORS.NS",
    "SUNPHARMA.NS", "TATASTEEL.NS",
    "BHARTIARTL.NS", "NTPC.NS",
    "NIFTYBEES.NS", "GOLDBEES.NS", "BANKBEES.NS",
]


def _load_scout_universe() -> List[str]:
    """Load tickers from scout_universe.txt. Falls back to defaults if file not found."""
    config_path = Path(__file__).parent.parent.parent / "scout_universe.txt"
    if not config_path.exists():
        return list(_SCOUT_UNIVERSE_DEFAULTS)
    tickers = []
    with open(config_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip inline comments (e.g., "NIFTYBEES.NS  # Nifty 50 ETF")
            ticker = line.split("#")[0].strip()
            if ticker:
                tickers.append(ticker)
    return tickers if tickers else list(_SCOUT_UNIVERSE_DEFAULTS)


SCOUT_UNIVERSE = _load_scout_universe()


class HMASWorkflow:
    """Main HMAS workflow orchestrator."""

    def __init__(
        self,
        memory_file: Optional[Path] = None,
        api_key: Optional[str] = None,
    ):
        self.llm = LLMClient(api_key=api_key)
        self.memory = MemoryMCP(memory_file)

        # Layer 1
        self.portfolio_context_agent = PortfolioContextAgent(self.memory)
        self.india_business_agent = IndiaBusinessAgent(india_news_mcp, market_mcp, self.llm)
        self.geopolitical_agent = GeopoliticalAgent(world_news_mcp, macro_mcp, self.llm)
        self.commodity_agent = CommodityAgent(world_news_mcp, macro_mcp, self.llm)
        self.sector_agent = SectorAgent(india_news_mcp, market_mcp, self.llm)
        self.quant_agent = QuantAgent(quant_mcp, self.llm)
        self.fundamentals_agent = FundamentalsAgent(fundamental_mcp, market_mcp, self.llm, self.memory)

        # Layer 2
        self.macro_lead = MacroLead(self.llm)
        self.micro_lead = MicroLead(self.llm)
        self.quant_lead = QuantLead(self.llm)

        # Layer 3
        self.chief_orchestrator = HMASChiefOrchestrator(self.memory, self.llm)

    def run_full_cycle(
        self,
        triggers: Optional[List[str]] = None,
        mode: str = "portfolio",
        watchlist_tickers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run a full HMAS analysis cycle.

        Args:
            triggers:          Activation triggers. None = full weekly review.
            mode:              "portfolio" (default), "general", or "scan" (watchlist buy scanner).
            watchlist_tickers: Tickers to scan for buy opportunities (required for mode="scan").

        Returns:
            Dict with briefs, buy_briefs, general_market_brief, state, and agent signal trail.
        """
        if triggers is None:
            triggers = ["scheduled_weekly_review"]

        state = HMASState()
        state.active_triggers = triggers
        active_agents = TriggerEvaluator.evaluate_triggers(triggers)

        # Determine which tickers need analysis
        _watchlist = watchlist_tickers or []

        # ── Load portfolio context ───────────────────────────────────────────
        print("[LOAD] Loading portfolio context...")
        if mode in ("portfolio", "scan"):
            portfolio_context = self.portfolio_context_agent.execute()
        else:
            portfolio_context = {}
        state.portfolio_context = portfolio_context

        # ── Progress helpers ─────────────────────────────────────────────────
        # +1 for FundamentalsAgent (runs in portfolio and scan modes)
        _fund_runs = mode in ("portfolio", "scan")
        total_l1 = (4 if mode == "general" else 5) + (1 if _fund_runs else 0)
        l1_step = [0]
        l2_step = [0]

        def _pkt_verdict(pkt) -> str:
            """Compact verdict from a SignalPacket: direction, confidence, signal count."""
            if not pkt:
                return ""
            d = pkt.dominant_direction.upper()
            c = pkt.confidence
            n = len(pkt.signals)
            return f"{d} ({c}, {n} signal{'s' if n != 1 else ''})"

        def _sc_verdict(sc) -> str:
            """Compact verdict from a Scorecard with inline flag indicators."""
            if not sc:
                return ""
            d = sc.direction.value.upper() if hasattr(sc.direction, "value") else str(sc.direction).upper()
            c = sc.confidence.value if hasattr(sc.confidence, "value") else str(sc.confidence)
            h = sc.horizon.value if hasattr(sc.horizon, "value") else str(sc.horizon)
            flags = []
            if sc.escalation_flag:
                flags.append("[!] ESCALATION")
            if sc.dissent_appendix:
                flags.append("[!] DISSENT")
            if sc.key_divergences:
                flags.append(f"[!] {len(sc.key_divergences)} DIVERGENCE(S)")
            flag_str = ("  " + "  ".join(flags)) if flags else ""
            return f"{d} ({c}, {h}){flag_str}"

        # ── Layer 1: Specialized agents ──────────────────────────────────────
        print("\n[LAYER 1] Running specialized agents...")

        if "india_business" in active_agents or "scheduled_weekly_review" in triggers:
            l1_step[0] += 1
            print(f"  [{l1_step[0]}/{total_l1}] India Business Agent...")
            state.india_business_signals = self.india_business_agent.execute(
                portfolio_context=portfolio_context, mode=mode
            )
            v = _pkt_verdict(state.india_business_signals)
            if v:
                print(f"      -> {v}")

        if "geopolitical" in active_agents or "scheduled_weekly_review" in triggers:
            l1_step[0] += 1
            print(f"  [{l1_step[0]}/{total_l1}] Geopolitical Agent...")
            state.geopolitical_signals = self.geopolitical_agent.execute(mode=mode)
            v = _pkt_verdict(state.geopolitical_signals)
            if v:
                print(f"      -> {v}")

        if "commodity" in active_agents or "scheduled_weekly_review" in triggers:
            l1_step[0] += 1
            print(f"  [{l1_step[0]}/{total_l1}] Commodity Agent...")
            state.commodity_signals = self.commodity_agent.execute(mode=mode)
            v = _pkt_verdict(state.commodity_signals)
            if v:
                print(f"      -> {v}")

        if "sector" in active_agents or "scheduled_weekly_review" in triggers:
            l1_step[0] += 1
            print(f"  [{l1_step[0]}/{total_l1}] Sector Agent...")
            state.sector_signals = self.sector_agent.execute(
                portfolio_context=portfolio_context, mode=mode
            )
            v = _pkt_verdict(state.sector_signals)
            if v:
                print(f"      -> {v}")

        # Quant Agent only runs in portfolio/scan mode (needs holdings or watchlist to analyze)
        if mode in ("portfolio", "scan") and (
            "quant" in active_agents or "scheduled_weekly_review" in triggers
        ):
            l1_step[0] += 1
            print(f"  [{l1_step[0]}/{total_l1}] Quant Agent...")
            state.quant_signals = self.quant_agent.execute(portfolio_context=portfolio_context)
            v = _pkt_verdict(state.quant_signals)
            if v:
                print(f"      -> {v}")

        # Fundamentals Agent runs in portfolio and scan modes
        if _fund_runs:
            l1_step[0] += 1
            print(f"  [{l1_step[0]}/{total_l1}] Fundamentals Agent...")
            state.fundamentals_signals = self.fundamentals_agent.execute(
                portfolio_context=portfolio_context
            )
            v = _pkt_verdict(state.fundamentals_signals)
            if v:
                print(f"      -> {v}")

        print("  [OK] Layer 1 complete.")

        # ── Layer 2: Domain Leads ────────────────────────────────────────────
        print("\n[LAYER 2] Running domain leads...")

        if state.geopolitical_signals or state.commodity_signals or "scheduled_weekly_review" in triggers:
            l2_step[0] += 1
            print(f"  [{l2_step[0]}/3] Macro Lead...")
            state.macro_lead_scorecard = self.macro_lead.execute(
                geopolitical_signals=state.geopolitical_signals,
                commodity_signals=state.commodity_signals,
                mode=mode,
            )
            v = _sc_verdict(state.macro_lead_scorecard)
            if v:
                print(f"      -> {v}")

        if state.india_business_signals or state.sector_signals or "scheduled_weekly_review" in triggers:
            l2_step[0] += 1
            print(f"  [{l2_step[0]}/3] Micro Lead...")
            state.micro_lead_scorecard = self.micro_lead.execute(
                india_business_signals=state.india_business_signals,
                sector_signals=state.sector_signals,
                portfolio_context=portfolio_context,
                mode=mode,
            )
            v = _sc_verdict(state.micro_lead_scorecard)
            if v:
                print(f"      -> {v}")

        # Quant Lead in portfolio and scan modes
        if mode in ("portfolio", "scan") and state.quant_signals and state.quant_signals.signals:
            l2_step[0] += 1
            print(f"  [{l2_step[0]}/3] Quant Lead...")
            state.quant_lead_modifier = self.quant_lead.execute(
                quant_signals=state.quant_signals,
                macro_lead_scorecard=state.macro_lead_scorecard,
                micro_lead_scorecard=state.micro_lead_scorecard,
                portfolio_context=portfolio_context,
            )
            v = _sc_verdict(state.quant_lead_modifier)
            if v:
                print(f"      -> {v}")

        print("  [OK] Layer 2 complete.")

        # ── Layer 3: Chief Orchestrator ──────────────────────────────────────
        print("\n[LAYER 3] Chief Orchestrator synthesizing...")
        result = self.chief_orchestrator.execute(
            portfolio_context=portfolio_context,
            macro_lead_scorecard=state.macro_lead_scorecard,
            micro_lead_scorecard=state.micro_lead_scorecard,
            quant_lead_scorecard=state.quant_lead_modifier,
            fundamentals_packet=state.fundamentals_signals,
            mode=mode,
            watchlist_tickers=_watchlist,
        )
        state.decision_briefs = result.get("briefs", [])
        print("  [OK] Orchestrator complete.")

        # Save memory after each portfolio/scan run
        if mode in ("portfolio", "scan"):
            self.memory.save_memory()

        fundamentals_dict = None
        if hasattr(state, "fundamentals_signals") and state.fundamentals_signals:
            fundamentals_dict = state.fundamentals_signals.to_dict()

        return {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "triggers": triggers,
            "anti_recency_check": result.get("anti_recency_check", ""),
            "briefs": [b.to_dict() for b in result.get("briefs", [])],
            "buy_briefs": [b.to_dict() for b in result.get("buy_briefs", [])],
            "general_market_brief": result.get("general_market_brief"),
            "signal_trail": {
                "india_business": state.india_business_signals.to_dict() if state.india_business_signals else None,
                "geopolitical": state.geopolitical_signals.to_dict() if state.geopolitical_signals else None,
                "commodity": state.commodity_signals.to_dict() if state.commodity_signals else None,
                "sector": state.sector_signals.to_dict() if state.sector_signals else None,
                "quant": state.quant_signals.to_dict() if state.quant_signals else None,
                "fundamentals": fundamentals_dict,
                "macro_lead": state.macro_lead_scorecard.to_dict() if state.macro_lead_scorecard else None,
                "micro_lead": state.micro_lead_scorecard.to_dict() if state.micro_lead_scorecard else None,
                "quant_lead": state.quant_lead_modifier.to_dict() if state.quant_lead_modifier else None,
            },
        }

    def run_scheduled_review(self) -> Dict[str, Any]:
        return self.run_full_cycle(triggers=["scheduled_weekly_review"], mode="portfolio")

    def run_general_market_analysis(self) -> Dict[str, Any]:
        return self.run_full_cycle(triggers=["scheduled_weekly_review"], mode="general")

    def run_scout(self, tickers: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Proactive buy opportunity scanner across the predefined Nifty universe.

        Fetches live technicals + fundamentals for SCOUT_UNIVERSE (or custom list),
        then asks the Orchestrator to identify the best setups for the coming week.
        Use this when you have no specific watchlist but want the system to surface ideas.

        Args:
            tickers: Override the default SCOUT_UNIVERSE list.
        """
        universe = tickers or SCOUT_UNIVERSE
        return self.run_full_cycle(
            triggers=["scheduled_weekly_review"],
            mode="scan",
            watchlist_tickers=universe,
        )

    def run_watchlist_scan(self, tickers: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run a buy opportunity scan for watchlist tickers.

        If tickers is None, reads the watchlist from portfolio memory.
        """
        if tickers is None:
            tickers = [w.ticker for w in self.memory.get_watchlist()]
        if not tickers:
            print("  [WARN] Watchlist is empty. Use 'watch TICKER' to add tickers.")
            return {
                "timestamp": datetime.now().isoformat(),
                "mode": "scan",
                "triggers": [],
                "briefs": [],
                "buy_briefs": [],
                "general_market_brief": None,
                "anti_recency_check": "",
                "signal_trail": {},
            }
        return self.run_full_cycle(
            triggers=["scheduled_weekly_review"],
            mode="scan",
            watchlist_tickers=tickers,
        )

    def run_emergency_analysis(self, trigger_type: str) -> Dict[str, Any]:
        trigger_map = {
            "rbi_announcement": ["rbi_fed_announcement"],
            "geopolitical_event": ["geopolitical_event"],
            "commodity_spike": ["commodity_spike"],
            "holding_move": ["holding_move_3pct"],
        }
        return self.run_full_cycle(
            triggers=trigger_map.get(trigger_type, ["scheduled_weekly_review"]),
            mode="portfolio",
        )

    # ── Display Methods ───────────────────────────────────────────────────────

    def print_full_report(self, result: Dict[str, Any], show_signal_trail: bool = True):
        """Print the complete HMAS report with explainability."""
        W = 80
        ts = result.get("timestamp", "")[:19].replace("T", " ")
        mode = result.get("mode", "portfolio").upper()

        print("\n" + "=" * W)
        print(f"  HMAS -- Hierarchical Multi-Agent Investment System")
        print(f"  {mode} MODE  |  {ts}")
        print("=" * W)

        # Anti-recency check
        arc = result.get("anti_recency_check", "")
        if arc:
            print(f"\n  12-MONTH CONTEXT CHECK")
            print(f"  {arc}")

        # General market brief (always shown)
        gmb: Optional[GeneralMarketBrief] = result.get("general_market_brief")
        if gmb:
            self._print_general_brief(gmb, W)

        # Agent digest — compact one-liner per agent, always shown
        trail = result.get("signal_trail", {})
        if any(v for v in trail.values() if v):
            self._print_agent_digest(trail, W)

        # Full signal trail — verbose reasoning chains, opt-in via --show-trail
        if show_signal_trail and any(v for v in trail.values() if v):
            self._print_signal_trail(trail, W)

        # Portfolio decision briefs (portfolio mode)
        briefs = result.get("briefs", [])
        if briefs:
            self._print_portfolio_briefs(briefs, W)

        # Watchlist buy briefs (scan mode)
        buy_briefs = result.get("buy_briefs", [])
        if buy_briefs:
            self._print_buy_briefs(buy_briefs, W)

        print("=" * W + "\n")

    def _print_general_brief(self, gmb: GeneralMarketBrief, W: int):
        def _wrap(text: str, indent: str = "  ") -> None:
            words = text.split()
            line = indent
            for word in words:
                if len(line) + len(word) + 1 > W - 2:
                    print(line)
                    line = indent + word + " "
                else:
                    line += word + " "
            if line.strip():
                print(line)

        print(f"\n{'-' * W}")
        print("  MARKET ENVIRONMENT")
        print(f"{'-' * W}")

        # Macro thesis
        direction_str = gmb.macro_direction.upper()
        print(f"  Macro: {direction_str}  ({gmb.macro_confidence} confidence | {gmb.macro_horizon})")
        print()
        _wrap(gmb.macro_thesis)

        if gmb.macro_dissent:
            print(f"\n  [!] Counter-signal worth noting: {gmb.macro_dissent}")

        # Micro
        if gmb.micro_thesis:
            print(f"\n  India domestic: {gmb.micro_direction.upper()}")
            _wrap(gmb.micro_thesis)

        # Sector signals (compact)
        if gmb.sector_signals:
            print("\n  Sector-by-sector:")
            for s in gmb.sector_signals:
                d = s.get("direction", "Neutral")
                sector = s.get("sector", "")
                signal = s.get("key_signal", "")
                icon = {"Bullish": "+", "Bearish": "-", "Neutral": " "}.get(d, " ")
                print(f"  [{icon}] {sector:<20} {signal[:W - 28]}")

        # Commodities
        print()
        if gmb.commodity_brent_impact:
            _wrap(f"Crude: {gmb.commodity_brent_impact}")
        if gmb.commodity_gold_signal:
            _wrap(f"Gold:  {gmb.commodity_gold_signal}")
        if gmb.flight_to_safety_active:
            print("  [!] FLIGHT-TO-SAFETY SIGNAL ACTIVE — risk-off across EM")

        # Week in review
        if gmb.week_in_review:
            print(f"\n  Week in review:")
            _wrap(gmb.week_in_review, indent="  ")

        # Top risks
        if gmb.top_risks:
            print("\n  Key risks to watch:")
            for r in gmb.top_risks:
                print(f"  - {str(r)[:W - 6]}")

        # ── Weekly opportunities ─────────────────────────────────────────────
        opps = gmb.weekly_opportunities
        if opps:
            print(f"\n{'-' * W}")
            print("  THIS WEEK'S OPPORTUNITIES")
            print(f"{'-' * W}")

            rec_order = {"BUY_NOW": 0, "WATCH_CLOSELY": 1, "MONITOR_FOR_LATER": 2, "AVOID_THIS_WEEK": 3}
            opps_sorted = sorted(opps, key=lambda x: rec_order.get(x.get("recommendation", "MONITOR_FOR_LATER"), 2))

            rec_labels = {
                "BUY_NOW":           "BUY NOW",
                "WATCH_CLOSELY":     "WATCH — trigger near",
                "MONITOR_FOR_LATER": "Monitor — not yet",
                "AVOID_THIS_WEEK":   "AVOID this week",
            }

            for opp in opps_sorted:
                name = opp.get("name", opp.get("ticker", "UNKNOWN"))
                rec = opp.get("recommendation", "MONITOR_FOR_LATER")
                conviction = opp.get("conviction", "low")
                label = rec_labels.get(rec, rec)
                print(f"\n  ── {name}  [{label}]  conviction: {conviction} ────────────")

                # Narrative first
                narrative = opp.get("narrative", "")
                if narrative:
                    _wrap(narrative)

                # Parameters
                print()
                entry = opp.get("entry_zone", "")
                stop = opp.get("stop_loss", "")
                horizon = opp.get("time_horizon", "")
                buy_t = opp.get("buy_trigger", "")
                avoid_t = opp.get("avoid_trigger", "")

                if rec != "AVOID_THIS_WEEK":
                    if entry:
                        print(f"  Entry: {entry}   Stop: {stop}   Horizon: {horizon}")
                    if buy_t:
                        print(f"  Buy if:    {str(buy_t)[:W - 12]}")
                if avoid_t:
                    print(f"  Avoid if:  {str(avoid_t)[:W - 12]}")
                key_risk = opp.get("key_risk", "")
                if key_risk:
                    print(f"  Key risk:  {str(key_risk)[:W - 12]}")

    def _print_agent_digest(self, trail: Dict, W: int):
        """Compact one-liner per agent — verdict, confidence, signal count, top signal."""
        print(f"\n{'-' * W}")
        print("  AGENT DIGEST")
        print(f"{'-' * W}")

        L1_AGENTS = [
            ("india_business", "India Business"),
            ("geopolitical",   "Geopolitical  "),
            ("commodity",      "Commodity     "),
            ("sector",         "Sector        "),
            ("quant",          "Quant         "),
            ("fundamentals",   "Fundamentals  "),
        ]
        L2_LEADS = [
            ("macro_lead", "Macro Lead"),
            ("micro_lead", "Micro Lead"),
            ("quant_lead", "Quant Lead"),
        ]

        def _dir4(s: str) -> str:
            s = s.upper()
            return {"BULLISH": "BULL", "BEARISH": "BEAR", "NEUTRAL": "NEUT"}.get(s, s[:4])

        def _top_signal(sigs: list) -> str:
            for s in sigs:
                dp = s.get("data_point") or s.get("india_impact") or ""
                dp = dp.strip()
                if dp:
                    return dp[:62]
            return ""

        any_l1 = any(trail.get(k) for k, _ in L1_AGENTS)
        any_l2 = any(trail.get(k) for k, _ in L2_LEADS)

        if any_l1:
            print("  Layer 1 — Specialized Agents")
            for key, label in L1_AGENTS:
                data = trail.get(key)
                if not data:
                    continue
                d = _dir4(data.get("dominant_direction", "neutral"))
                c = data.get("confidence", "").ljust(6)
                sigs = data.get("signals", [])
                n = len(sigs)
                top = _top_signal(sigs)
                line = f"  [L1] {label}   {d}  {c}  {n} sig"
                if top:
                    line += f"  |  {top}"
                # Flight-to-safety flag
                if any(s.get("flag") == "FLIGHT_TO_SAFETY" for s in sigs):
                    line += "  [!] FLIGHT-TO-SAFETY"
                print(line)
            print()

        if any_l2:
            print("  Layer 2 — Domain Leads")
            for key, label in L2_LEADS:
                data = trail.get(key)
                if not data:
                    continue
                d = _dir4(data.get("direction", data.get("dominant_direction", "neutral")))
                c = data.get("confidence", "").ljust(6)
                h = data.get("horizon", "")
                print(f"  [L2] {label}   {d}  {c}  {h}")
                if data.get("escalation_flag"):
                    reason = (data.get("escalation_reason") or "")[:70]
                    print(f"       [!] ESCALATION: {reason}")
                da = data.get("dissent_appendix")
                if da:
                    sig = da.get("anomaly_significance", "?")
                    note = (da.get("dissent_summary") or "")[:65]
                    print(f"       [!] DISSENT ({sig}): {note}")
                for div in (data.get("key_divergences") or [])[:2]:
                    print(f"       [!] DIVERGENCE: {str(div)[:65]}")
            print()

    def _print_signal_trail(self, trail: Dict, W: int):
        print(f"\n{'-' * W}")
        print("  SIGNAL TRAIL  (reasoning transparency -- how each agent reached its conclusion)")
        print(f"{'-' * W}")

        agent_labels = {
            "india_business": "[L1] India Business Agent",
            "geopolitical":   "[L1] Geopolitical Agent",
            "commodity":      "[L1] Commodity Agent",
            "sector":         "[L1] Sector Agent",
            "quant":          "[L1] Quant Agent",
            "fundamentals":   "[L1] Fundamentals Agent",
            "macro_lead":     "[L2] Macro Lead",
            "micro_lead":     "[L2] Micro Lead",
            "quant_lead":     "[L2] Quant Lead",
        }

        for key, label in agent_labels.items():
            data = trail.get(key)
            if not data:
                continue

            direction = data.get("dominant_direction", data.get("direction", "")).upper()
            confidence = data.get("confidence", "")
            tag = f"  {label}"
            if direction:
                tag += f"  ->  {direction}"
                if confidence:
                    tag += f" ({confidence})"
            print(tag)

            chain = data.get("reasoning_chain", [])
            for step in chain:
                # Wrap long lines
                step_str = str(step)
                print(f"    {step_str[:120]}")
            if chain:
                print()

            # Dissent appendix for Macro Lead
            if key == "macro_lead" and data.get("dissent_appendix"):
                da = data["dissent_appendix"]
                print(f"    [!] DISSENT APPENDIX ({da.get('anomaly_significance','?')} significance):")
                print(f"      {da.get('dissent_summary', '')}")
                print()

            # Escalation flag for Micro Lead
            if key == "micro_lead" and data.get("escalation_flag"):
                print(f"    [!] ESCALATION: {data.get('escalation_reason', '')}\n")

            # Divergences for Quant Lead
            if key == "quant_lead" and data.get("key_divergences"):
                for div in data["key_divergences"]:
                    print(f"    [!] DIVERGENCE: {div}")
                print()

    def _print_portfolio_briefs(self, briefs: List[Dict], W: int):
        print(f"\n{'-' * W}")
        print("  PORTFOLIO DECISIONS")
        print(f"{'-' * W}")

        flag_icons = {"HOLD": "HOLD", "WATCH": "WATCH!", "EXIT_CONDITION_APPROACHING": "EXIT >>"}
        bst_labels = {"PASS": "Fresh buyer test: PASS", "FAIL": "Fresh buyer test: FAIL [sunk cost risk]"}

        for b in briefs:
            flag = b.get("flag", "HOLD")
            bst = b.get("blank_slate_test", "PASS")
            ticker = b.get("ticker", "UNKNOWN")

            print(f"\n  ── {ticker}  [{flag_icons.get(flag, flag)}] ──────────────────────────────")

            # Narrative first — this is the human-readable explanation
            narrative = b.get("narrative", "")
            if narrative:
                # Word-wrap at W-4 chars
                words = narrative.split()
                line = "  "
                for word in words:
                    if len(line) + len(word) + 1 > W - 2:
                        print(line)
                        line = "  " + word + " "
                    else:
                        line += word + " "
                if line.strip():
                    print(line)

            # Supporting detail (compact, below the narrative)
            print()
            print(f"  Thesis: {b.get('thesis_status','')}  |  Technical: {b.get('technical_alignment','')}  |  {bst_labels.get(bst, bst)}")
            if b.get("blank_slate_notes") and bst == "FAIL":
                bsn = b["blank_slate_notes"]
                print(f"  {bsn[:W - 4]}")

            # Reasoning chain behind --show-trail (shown here always as it's compact)
            chain = b.get("reasoning_chain", [])
            if chain:
                print(f"\n  Why I reached this conclusion:")
                for step in chain:
                    _wrapped = str(step)
                    print(f"    {_wrapped[:W - 6]}")

    def _print_buy_briefs(self, buy_briefs: List[Dict], W: int):
        print(f"\n{'-' * W}")
        print("  BUY OPPORTUNITY SCAN")
        print(f"{'-' * W}")

        def _wrap(text: str, indent: str = "  ") -> None:
            words = text.split()
            line = indent
            for word in words:
                if len(line) + len(word) + 1 > W - 2:
                    print(line)
                    line = indent + word + " "
                else:
                    line += word + " "
            if line.strip():
                print(line)

        flag_labels = {
            "BUY_NOW":        "BUY NOW",
            "WAIT_FOR_ENTRY": "WATCH — wait for trigger",
            "AVOID":          "AVOID this week",
        }

        # Sort: BUY_NOW first, then WAIT, then AVOID
        sorted_briefs = sorted(
            buy_briefs,
            key=lambda x: {"BUY_NOW": 0, "WAIT_FOR_ENTRY": 1, "AVOID": 2}.get(x.get("flag", "AVOID"), 2)
        )

        for b in sorted_briefs:
            flag = b.get("flag", "WAIT_FOR_ENTRY")
            ticker = b.get("ticker", "UNKNOWN")
            conviction = b.get("conviction", "low")

            label = flag_labels.get(flag, flag)
            print(f"\n  ── {ticker}  [{label}]  conviction: {conviction} ────────────────")

            # Narrative is the headline — show it first and prominently
            narrative = b.get("narrative", "")
            if narrative:
                _wrap(narrative)
            else:
                # Fallback to setup + buy/avoid condition if no narrative
                if b.get("setup"):
                    print(f"  {b['setup']}")

            # Parameters (compact block below the narrative)
            print()
            if flag != "AVOID":
                entry = b.get("entry_zone", "N/A")
                stop = b.get("stop_loss", "N/A")
                horizon = b.get("time_horizon", "N/A")
                buy_cond = b.get("buy_condition", "")
                print(f"  Entry: {entry}   Stop: {stop}   Horizon: {horizon}")
                if buy_cond and buy_cond not in ("N/A", "All conditions met — act now"):
                    print(f"  Trigger: {buy_cond[:W - 12]}")
            print(f"  Fundamentals: {b.get('fundamental_quality','?')}  |  Valuation: {b.get('valuation_status','?')}  |  Macro: {b.get('macro_alignment','?')}")

            # Reasoning chain (detailed, for --show-trail)
            chain = b.get("reasoning_chain", [])
            if chain:
                print(f"\n  Supporting analysis:")
                for step in chain:
                    print(f"    {str(step)[:W - 6]}")

    def print_decision_briefs(self, result: Dict[str, Any]):
        """Backwards-compatible alias — calls print_full_report."""
        self.print_full_report(result, show_signal_trail=False)
