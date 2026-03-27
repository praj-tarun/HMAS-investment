"""
HMAS v2 Workflow — ScoutWorkflow and PortfolioWorkflow.

ScoutWorkflow  → python run.py scout
PortfolioWorkflow → python run.py portfolio

Both workflows share Phases 0 and 1 (intelligence + macro chain).
The macro chain is cached for 2 hours so back-to-back runs don't double-call gpt-4o.

Parallel execution via ThreadPoolExecutor:
  - Phase 0: all 4 intel agents run simultaneously
  - Phase 3: all stock/holding research agents run simultaneously
"""

from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.core.llm_client import LLMClient
from src.core.types import MacroChainOutput, StockStory, HoldingAction
from src.memory.memory_mcp import MemoryMCP

from src.intelligence.news_intel_agent import NewsIntelAgent
from src.intelligence.global_markets_agent import GlobalMarketsAgent
from src.intelligence.geopolitics_agent import GeopoliticsAgent
from src.intelligence.macro_data_agent import MacroDataAgent

from src.reasoning.macro_chain_agent import MacroChainAgent
from src.reasoning.web_search_universe import WebSearchUniverseAgent
from src.reasoning.source_verifier import SourceVerifier

from src.research.stock_research_agent import StockResearchAgent
from src.research.holding_research_agent import HoldingResearchAgent

from src.selection.scout_selection_agent import ScoutSelectionAgent
from src.selection.portfolio_advisor_agent import PortfolioAdvisorAgent


# ── Shared data fetch ─────────────────────────────────────────────────────────

def _load_live_market_data(tickers: List[str], skip: bool = False) -> Dict[str, Any]:
    """Pre-populate the global MCPs with live data (reuses existing fetcher)."""
    if skip or not tickers:
        return {}
    try:
        from src.data.market_fetcher import populate_mcps
        return populate_mcps(tickers) or {}
    except Exception as exc:
        print(f"  [WARN] market_fetcher failed: {exc}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# ScoutWorkflow
# ─────────────────────────────────────────────────────────────────────────────

class ScoutWorkflow:
    """
    Full scout pipeline: intelligence → macro chain → web universe → verify
    → parallel stock research → top-5 selection.
    """

    def __init__(self, memory_file: Optional[Path] = None, api_key: Optional[str] = None):
        self.llm = LLMClient(api_key=api_key)
        self.memory = MemoryMCP(memory_file)

        # Agents
        self.news_agent       = NewsIntelAgent(self.llm)
        self.markets_agent    = GlobalMarketsAgent(self.llm)
        self.geo_agent        = GeopoliticsAgent(self.llm)
        self.macro_data_agent = MacroDataAgent(self.llm)

        self.macro_chain_agent = MacroChainAgent(self.llm)
        self.universe_agent    = WebSearchUniverseAgent(self.llm)
        self.verifier          = SourceVerifier()

        self.stock_research_agent = StockResearchAgent(self.llm)
        self.selection_agent      = ScoutSelectionAgent(self.llm)

    def run(self, previous_context: str = "") -> Dict[str, Any]:
        """Execute the full scout pipeline. Returns a structured result dict."""
        import os
        start = datetime.now()
        print("\n[SCOUT v2] Starting HMAS v2 Scout pipeline...")
        if not os.getenv("TAVILY_API_KEY") or os.getenv("TAVILY_API_KEY") == "tvly-your-key-here":
            print("  [!] TAVILY_API_KEY not set — web search disabled, using fallback sector map")
            print("      For macro-driven universe: add TAVILY_API_KEY to .env (free at tavily.com)")

        # ── Phase 0: Intelligence Gathering (parallel) ────────────────────────
        print("\n[Phase 0] Intelligence Gathering (4 agents, parallel)...")
        intel_packets = self._run_intel_parallel()

        news_pkt     = intel_packets.get("news")
        markets_pkt  = intel_packets.get("markets")
        geo_pkt      = intel_packets.get("geo")
        macro_pkt    = intel_packets.get("macro")

        # ── Phase 1: Macro Chain Reasoning ───────────────────────────────────
        print("\n[Phase 1] Macro Chain Reasoning...")
        macro_chain: MacroChainOutput = self.macro_chain_agent.run(
            news_packet=news_pkt,
            global_markets_packet=markets_pkt,
            geopolitics_packet=geo_pkt,
            macro_data_packet=macro_pkt,
            previous_context=previous_context,
        )
        print(f"  Causal chain: {macro_chain.causal_chain[:120]}...")
        print(f"  Explore: {macro_chain.explore_themes}  |  Avoid: {macro_chain.avoid_themes}")

        # ── Phase 2A: Web Search Universe ────────────────────────────────────
        print("\n[Phase 2A] Web Search Universe...")
        universe_result = self.universe_agent.run(macro_chain.explore_themes)
        raw_candidates = universe_result.get("raw_candidates", [])

        # ── Phase 2B: Source Verification ────────────────────────────────────
        print("[Phase 2B] Source Verification (3-gate)...")
        verify_result = self.verifier.verify(raw_candidates)
        verified = verify_result.get("verified", [])
        verified_tickers = [v["ticker"] for v in verified]

        if not verified_tickers:
            print("  [WARN] No verified candidates — falling back to defaults")
            from src.core.workflow import SCOUT_UNIVERSE
            verified_tickers = SCOUT_UNIVERSE[:10]

        print(f"  {len(verified_tickers)} tickers proceeding to research: {verified_tickers}")

        # ── Phase 3: Stock Deep Dive (parallel) ──────────────────────────────
        print(f"\n[Phase 3] Stock Research ({len(verified_tickers)} stocks, parallel)...")
        stories = self._run_stock_research_parallel(verified_tickers, macro_chain)
        valid_stories = [s for s in stories if s and s.opportunity_type != "error"]
        print(f"  {len(valid_stories)} stock stories produced")

        # ── Phase 4: Selection ────────────────────────────────────────────────
        print("\n[Phase 4] Selection — picking Top 5...")
        selection = self.selection_agent.run(valid_stories, macro_chain)

        elapsed = (datetime.now() - start).total_seconds()
        print(f"\n[SCOUT v2] Complete in {elapsed:.0f}s")

        return {
            "timestamp": datetime.now().isoformat(),
            "mode": "scout_v2",
            "elapsed_seconds": elapsed,
            "macro_chain": macro_chain.to_dict(),
            "intel_packets": {
                "news": news_pkt,
                "global_markets": markets_pkt,
                "geopolitics": geo_pkt,
                "macro_data": macro_pkt,
            },
            "universe": {
                "raw_count": len(raw_candidates),
                "verified_count": len(verified_tickers),
                "verified_tickers": verified_tickers,
                "rejected": verify_result.get("rejected", {}),
                "fallback_used": universe_result.get("fallback_used", False),
            },
            "stories": [s.to_dict() for s in valid_stories],
            "selection": selection,
        }

    # ── Parallel helpers ──────────────────────────────────────────────────────

    def _run_intel_parallel(self) -> Dict[str, Optional[Dict]]:
        """Run all 4 intel agents concurrently."""
        agents = {
            "news":    self.news_agent,
            "markets": self.markets_agent,
            "geo":     self.geo_agent,
            "macro":   self.macro_data_agent,
        }
        results: Dict[str, Optional[Dict]] = {k: None for k in agents}

        with ThreadPoolExecutor(max_workers=4) as ex:
            future_map: Dict[Future, str] = {
                ex.submit(agent.run): key
                for key, agent in agents.items()
            }
            for future in as_completed(future_map):
                key = future_map[future]
                try:
                    results[key] = future.result()
                except Exception as exc:
                    print(f"  [WARN] Intel agent '{key}' failed: {exc}")
        return results

    def _run_stock_research_parallel(
        self,
        tickers: List[str],
        macro_chain: MacroChainOutput,
        max_workers: int = 5,
    ) -> List[Optional[StockStory]]:
        """Run StockResearchAgent for each ticker concurrently."""
        results: List[Optional[StockStory]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            future_map: Dict[Future, str] = {
                ex.submit(self.stock_research_agent.run, ticker, macro_chain): ticker
                for ticker in tickers
            }
            for future in as_completed(future_map):
                ticker = future_map[future]
                try:
                    story = future.result()
                    results.append(story)
                    print(f"    [Done] {ticker}: score={story.score:.0f} conviction={story.conviction}")
                except Exception as exc:
                    print(f"  [WARN] StockResearch({ticker}) failed: {exc}")
        return results

    # ── Output printing ───────────────────────────────────────────────────────

    def print_report(self, result: Dict[str, Any], show_trail: bool = False):
        """Print the scout report to console."""
        W = 80
        ts = result.get("timestamp", "")[:19].replace("T", " ")
        elapsed = result.get("elapsed_seconds", 0)

        print("\n" + "=" * W)
        print(f"  HMAS v2 — SCOUT MODE  |  {ts}  ({elapsed:.0f}s)")
        print("=" * W)

        macro = result.get("macro_chain", {})
        _print_market_brief(macro, W)

        if show_trail:
            _print_intel_digest(result.get("intel_packets", {}), W)

        _print_universe_stats(result.get("universe", {}), W)
        _print_top5(result.get("selection", {}), W)
        _print_all_stories(result.get("stories", []), W)
        print("=" * W + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# PortfolioWorkflow
# ─────────────────────────────────────────────────────────────────────────────

class PortfolioWorkflow:
    """
    Full portfolio pipeline: intelligence → macro chain → parallel holding research
    → portfolio advisor synthesis.

    The macro chain is shared with ScoutWorkflow (cached, 2-hour TTL).
    """

    def __init__(self, memory_file: Optional[Path] = None, api_key: Optional[str] = None):
        self.llm = LLMClient(api_key=api_key)
        self.memory = MemoryMCP(memory_file)

        self.news_agent       = NewsIntelAgent(self.llm)
        self.markets_agent    = GlobalMarketsAgent(self.llm)
        self.geo_agent        = GeopoliticsAgent(self.llm)
        self.macro_data_agent = MacroDataAgent(self.llm)

        self.macro_chain_agent   = MacroChainAgent(self.llm)
        self.holding_research    = HoldingResearchAgent(self.llm)
        self.portfolio_advisor   = PortfolioAdvisorAgent(self.llm)

    def run(self, scout_results: Optional[Dict] = None, previous_context: str = "") -> Dict[str, Any]:
        """
        Execute the full portfolio pipeline.

        Args:
            scout_results:     If scout was already run this session, pass its results.
            previous_context:  Summary of the previous portfolio run for agent learning.
        """
        start = datetime.now()

        # Load holdings
        ctx = self.memory.get_portfolio_context()
        holdings = ctx.get("current_holdings", [])
        if not holdings:
            return {
                "timestamp": datetime.now().isoformat(),
                "mode": "portfolio_v2",
                "error": "Portfolio is empty. Add holdings with: python run.py add TICKER.NS",
                "holdings_actions": [],
            }

        print(f"\n[PORTFOLIO v2] Starting pipeline for {len(holdings)} holding(s)...")

        # ── Phase 0+1: Intelligence + Macro Chain ────────────────────────────
        print("\n[Phase 0] Intelligence Gathering (parallel)...")
        intel_packets = self._run_intel_parallel()

        print("\n[Phase 1] Macro Chain Reasoning...")
        macro_chain: MacroChainOutput = self.macro_chain_agent.run(
            news_packet=intel_packets.get("news"),
            global_markets_packet=intel_packets.get("markets"),
            geopolitics_packet=intel_packets.get("geo"),
            macro_data_packet=intel_packets.get("macro"),
            previous_context=previous_context,
        )

        # ── Phase 2: Holding Deep Dive (parallel) ────────────────────────────
        print(f"\n[Phase 2] Holding Research ({len(holdings)} holdings, parallel)...")
        holding_actions = self._run_holding_research_parallel(
            holdings, macro_chain, previous_context=previous_context
        )
        valid_actions = [a for a in holding_actions if a]
        print(f"  {len(valid_actions)} holding reports complete")

        # ── Phase 3: Portfolio Synthesis ─────────────────────────────────────
        print("\n[Phase 3] Portfolio Synthesis...")
        advisor_result = self.portfolio_advisor.run(
            holding_actions=valid_actions,
            macro_chain=macro_chain,
            scout_results=scout_results,
        )

        # Save memory
        self.memory.save_memory()

        elapsed = (datetime.now() - start).total_seconds()
        print(f"\n[PORTFOLIO v2] Complete in {elapsed:.0f}s")

        return {
            "timestamp": datetime.now().isoformat(),
            "mode": "portfolio_v2",
            "elapsed_seconds": elapsed,
            "macro_chain": macro_chain.to_dict(),
            "intel_packets": intel_packets,
            "holding_actions": [a.to_dict() for a in valid_actions],
            "advisor": advisor_result,
        }

    # ── Parallel helpers ──────────────────────────────────────────────────────

    def _run_intel_parallel(self) -> Dict[str, Optional[Dict]]:
        agents = {
            "news":    self.news_agent,
            "markets": self.markets_agent,
            "geo":     self.geo_agent,
            "macro":   self.macro_data_agent,
        }
        results: Dict[str, Optional[Dict]] = {k: None for k in agents}
        with ThreadPoolExecutor(max_workers=4) as ex:
            future_map = {ex.submit(agent.run): key for key, agent in agents.items()}
            for future in as_completed(future_map):
                key = future_map[future]
                try:
                    results[key] = future.result()
                except Exception as exc:
                    print(f"  [WARN] Intel agent '{key}' failed: {exc}")
        return results

    def _run_holding_research_parallel(
        self,
        holdings: List[Dict],
        macro_chain: MacroChainOutput,
        max_workers: int = 5,
        previous_context: str = "",
    ) -> List[Optional[HoldingAction]]:
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            future_map = {
                ex.submit(self.holding_research.run, h, macro_chain, previous_context): h.get("ticker", "?")
                for h in holdings
            }
            for future in as_completed(future_map):
                ticker = future_map[future]
                try:
                    action = future.result()
                    results.append(action)
                    print(f"    [Done] {ticker}: {action.action} | thesis={action.thesis_status}")
                except Exception as exc:
                    print(f"  [WARN] HoldingResearch({ticker}) failed: {exc}")
        return results

    # ── Output printing ───────────────────────────────────────────────────────

    def print_report(self, result: Dict[str, Any], show_trail: bool = False):
        """Print the portfolio report to console."""
        W = 80
        ts = result.get("timestamp", "")[:19].replace("T", " ")
        elapsed = result.get("elapsed_seconds", 0)

        if result.get("error"):
            print(f"\n[!] {result['error']}\n")
            return

        print("\n" + "=" * W)
        print(f"  HMAS v2 — PORTFOLIO MODE  |  {ts}  ({elapsed:.0f}s)")
        print("=" * W)

        macro = result.get("macro_chain", {})
        _print_market_brief(macro, W)

        if show_trail:
            _print_intel_digest(result.get("intel_packets", {}), W)

        _print_portfolio_decisions(result.get("advisor", {}), W)
        print("=" * W + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Shared print helpers
# ─────────────────────────────────────────────────────────────────────────────

def _wrap(text: str, indent: str = "  ", width: int = 78) -> None:
    words = text.split()
    line = indent
    for word in words:
        if len(line) + len(word) + 1 > width:
            print(line)
            line = indent + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)


def _print_market_brief(macro: Dict, W: int):
    print(f"\n{'-' * W}")
    print("  MARKET BRIEF")
    print(f"{'-' * W}")
    regime = macro.get("market_regime", "unknown").upper()
    conf = macro.get("regime_confidence", "?")
    print(f"  Regime: {regime}  ({conf} confidence)")
    print()
    chain = macro.get("causal_chain", "")
    if chain:
        _wrap(chain)
    overlay = macro.get("india_overlay", {})
    if overlay:
        print()
        print(f"  Rupee: {overlay.get('rupee_outlook','?')}  |  "
              f"RBI: {overlay.get('rbi_stance','?')}  |  "
              f"FII: {overlay.get('fii_sentiment','?')}  |  "
              f"PE: {overlay.get('pe_impact','?')}")
    explore = macro.get("explore_themes", [])
    avoid = macro.get("avoid_themes", [])
    if explore:
        print(f"\n  Explore: {', '.join(explore)}")
    if avoid:
        print(f"  Avoid:   {', '.join(avoid)}")
    risk = macro.get("india_overlay", {}).get("key_risk", "")
    if risk:
        print(f"\n  Key risk: {risk}")


def _print_intel_digest(intel: Dict, W: int):
    print(f"\n{'-' * W}")
    print("  INTELLIGENCE DIGEST")
    print(f"{'-' * W}")
    labels = [
        ("news", "News Intel     "),
        ("global_markets", "Global Markets "),
        ("geopolitics", "Geopolitics    "),
        ("macro_data", "Macro Data     "),
    ]
    for key, label in labels:
        pkt = intel.get(key)
        if not pkt:
            continue
        regime = pkt.get("regime", "?")
        conf = pkt.get("confidence", "?")
        sigs = pkt.get("key_signals", [])
        top = sigs[0] if sigs else ""
        print(f"  [{label}] {regime.upper():<15} ({conf})  |  {top[:50]}")


def _print_universe_stats(universe: Dict, W: int):
    if not universe:
        return
    print(f"\n{'-' * W}")
    raw = universe.get("raw_count", 0)
    verified = universe.get("verified_count", 0)
    fallback = universe.get("fallback_used", False)
    tickers = universe.get("verified_tickers", [])
    fb_note = " [fallback sector map used]" if fallback else ""
    print(f"  Universe: {raw} raw candidates -> {verified} verified{fb_note}")
    if tickers:
        print(f"  Researching: {', '.join(tickers)}")


def _print_top5(selection: Dict, W: int):
    top5 = selection.get("top5", [])
    if not top5:
        print("\n  No opportunities selected.")
        return

    print(f"\n{'-' * W}")
    print("  THIS WEEK'S TOP 5 OPPORTUNITIES")
    print(f"{'-' * W}")

    rec_labels = {
        "BUY_NOW":           "BUY NOW",
        "WATCH_CLOSELY":     "WATCH — trigger near",
        "MONITOR_FOR_LATER": "Monitor",
    }

    for item in top5:
        rank = item.get("rank", "?")
        ticker = item.get("ticker", "?")
        rec = item.get("recommendation", "MONITOR_FOR_LATER")
        conviction = item.get("conviction", "?")
        score = item.get("final_score", "?")
        label = rec_labels.get(rec, rec)

        print(f"\n  ── #{rank} {ticker}  [{label}]  conviction: {conviction}  score: {score}/100 ──")

        story = item.get("story", "")
        if story:
            _wrap(story)

        print()
        entry = item.get("entry_zone", "N/A")
        stop = item.get("stop_loss", "N/A")
        horizon = item.get("time_horizon", "N/A")
        risk = item.get("key_risk", "")
        why = item.get("why_selected", "")

        print(f"  Entry: {entry}   Stop: {stop}   Horizon: {horizon}")
        if why:
            print(f"  Why: {why}")
        if risk:
            print(f"  Risk: {risk}")

    sel_reasoning = selection.get("selection_reasoning", [])
    if sel_reasoning:
        print(f"\n  Selection rationale:")
        for r in sel_reasoning[:2]:
            _wrap(r, indent="    ")


def _print_all_stories(stories: List[Dict], W: int):
    """Print a condensed research note for every stock analysed."""
    if not stories:
        return

    # Sort: macro_tailwind / value_play / momentum first, avoid last
    order = {"macro_tailwind": 0, "value_play": 1, "momentum": 2, "defensive": 3, "avoid": 4}
    sorted_stories = sorted(stories, key=lambda s: (order.get(s.get("opportunity_type","avoid"), 5), -s.get("score", 0)))

    print(f"\n{'-' * W}")
    print("  FULL RESEARCH NOTES  (all stocks analysed this run)")
    print(f"{'-' * W}")

    type_icons = {
        "macro_tailwind": "▲ MACRO TAILWIND",
        "value_play":     "◆ VALUE PLAY",
        "momentum":       "→ MOMENTUM",
        "defensive":      "■ DEFENSIVE",
        "avoid":          "✕ AVOID NOW",
    }

    for s in sorted_stories:
        ticker      = s.get("ticker", "?")
        score       = s.get("score", 0)
        opp_type    = s.get("opportunity_type", "avoid")
        conviction  = s.get("conviction", "low")
        entry       = s.get("entry_zone", "N/A")
        stop        = s.get("stop_loss", "N/A")
        horizon     = s.get("time_horizon", "N/A")
        story       = s.get("story", "")
        technicals  = s.get("technicals_summary", "")
        macro_align = s.get("macro_alignment", "")
        key_risk    = s.get("key_risk", "")

        label = type_icons.get(opp_type, opp_type.upper())
        print(f"\n  {ticker:<18} [{label}]  score={score:.0f}/100  conviction={conviction}")

        if macro_align:
            print(f"  Macro: {macro_align[:90]}")

        if story:
            _wrap(story)

        # Entry trigger / what to watch
        if opp_type != "avoid":
            print(f"  Entry: {entry}   Stop: {stop}   Horizon: {horizon}")
        else:
            # For avoid stocks, show what would change the thesis
            if entry and entry.upper() != "AVOID":
                print(f"  Watch entry: {entry}   Stop: {stop}")
            else:
                print(f"  Status: Not actionable now — monitor for conditions to change")

        if technicals:
            print(f"  Technicals: {technicals[:90]}")
        if key_risk:
            print(f"  Risk: {key_risk[:90]}")


def _print_portfolio_decisions(advisor: Dict, W: int):
    if not advisor:
        return

    # Market overlay summary
    overlay = advisor.get("macro_overlay_summary", "")
    if overlay:
        print(f"\n{'-' * W}")
        print("  MACRO OVERLAY")
        print(f"{'-' * W}")
        _wrap(overlay)

    # Per-holding decisions
    actions = advisor.get("holdings_actions", [])
    if actions:
        print(f"\n{'-' * W}")
        print("  PORTFOLIO DECISIONS")
        print(f"{'-' * W}")

        action_icons = {"HOLD": "HOLD", "ADD": "ADD +", "TRIM": "TRIM ↓", "EXIT": "EXIT >>"}

        for a in actions:
            ticker = a.get("ticker", "?")
            action = a.get("confirmed_action", "HOLD")
            bst = a.get("blank_slate_test", "PASS")
            pnl = a.get("pnl_pct", 0)
            pnl_str = f"{pnl:+.1f}%" if pnl else "N/A"
            changed = a.get("action_changed_from")

            icon = action_icons.get(action, action)
            change_note = f"  (changed from {changed})" if changed else ""
            print(f"\n  ── {ticker}  [{icon}]{change_note}  P&L: {pnl_str}")

            if bst == "FAIL":
                bsn = a.get("blank_slate_note", "")
                print(f"  [!] SUNK COST FLAG: {bsn[:100]}")

            narrative = a.get("narrative", "")
            if narrative:
                _wrap(narrative)

            macro_align = a.get("macro_overlay", "")
            if macro_align:
                print(f"  Macro: {macro_align[:80]}")

    # Concentration risks
    risks = advisor.get("concentration_risks", [])
    if risks:
        print(f"\n{'-' * W}")
        print("  CONCENTRATION RISKS")
        print(f"{'-' * W}")
        for r in risks:
            print(f"  [!] {r.get('factor','?')}: {r.get('exposed_tickers',[])} -> {r.get('risk','')[:100]}")

    # Scout cross-reference
    crossref = advisor.get("scout_crossref", {})
    gap_fillers = crossref.get("gap_fillers", [])
    overweight = crossref.get("overweight_warnings", [])
    if gap_fillers or overweight:
        print(f"\n{'-' * W}")
        print("  SCOUT CROSS-REFERENCE")
        print(f"{'-' * W}")
        for g in gap_fillers:
            print(f"  [Opportunity] {g}")
        for o in overweight:
            print(f"  [Overweight]  {o}")

    # Sunk cost summary
    scs = advisor.get("sunk_cost_summary", {})
    if scs and scs.get("fail_count", 0) > 0:
        print(f"\n  [!] SUNK COST SUMMARY: {scs.get('fail_count',0)} holding(s) fail blank-slate test: "
              f"{scs.get('affected_tickers',[])}")

    # Portfolio-level advice
    advice = advisor.get("portfolio_level_advice", "")
    if advice:
        print(f"\n{'-' * W}")
        print("  PORTFOLIO-LEVEL ADVICE")
        print(f"{'-' * W}")
        _wrap(advice)
