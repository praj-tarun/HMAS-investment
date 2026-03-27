"""
Layer 1 Agents — Specialized agents that produce signal packets via LLM reasoning.

Each agent:
- Has a system prompt encoding the exact COT from the blueprint
- Formats its available MCP data into a structured user message
- Calls OpenAI gpt-4o-mini for reasoning
- Maps the JSON response to a SignalPacket
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import asdict

from src.core.types import SignalPacket, Layer1Agent
from src.core.llm_client import LLMClient
from src.memory.memory_mcp import MemoryMCP, get_portfolio_context_string
from src.mcp_tools.mcp_tools import (
    IndiaNewsMCP, WorldNewsMCP, MarketMCP, QuantMCP, MacroMCP, FundamentalMCP,
)


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio Context Agent  (no LLM — pure memory retrieval and formatting)
# ─────────────────────────────────────────────────────────────────────────────

class PortfolioContextAgent(Layer1Agent):
    """
    Loads Memory MCP and structures portfolio context for all downstream agents.
    Does NOT call an LLM — this is a data retrieval and formatting step only.
    Output is injected into every Layer 2 Lead and the Chief Orchestrator.
    """

    def __init__(self, memory: MemoryMCP):
        super().__init__("Portfolio Context Agent")
        self.memory = memory

    def execute(self, **kwargs) -> Dict[str, Any]:
        ctx = self.memory.get_portfolio_context()
        ctx["timestamp"] = datetime.now().isoformat()
        ctx["context_string"] = get_portfolio_context_string(self.memory)

        # Drawdown context — named state for sunk cost awareness
        pnl = ctx.get("portfolio_pnl_pct", 0.0)
        if pnl < -10:
            ctx["drawdown_context"] = f"Portfolio is in significant drawdown ({pnl:+.1f}%). High sunk cost risk — apply extra scrutiny to blank slate tests."
        elif pnl < -5:
            ctx["drawdown_context"] = f"Portfolio is in moderate drawdown ({pnl:+.1f}%). Monitor sunk cost bias on individual positions."
        elif pnl > 10:
            ctx["drawdown_context"] = f"Portfolio is in positive territory ({pnl:+.1f}%). No drawdown pressure."
        else:
            ctx["drawdown_context"] = f"Portfolio P&L is near flat ({pnl:+.1f}%)."

        # Flag any positions with invalidated theses still held
        ctx["high_conviction_flags"] = [
            it["ticker"] for it in ctx.get("invalidated_theses", [])
        ]

        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# India Business Agent
# ─────────────────────────────────────────────────────────────────────────────

_INDIA_BUSINESS_SYSTEM = """
You are the India Business Agent in HMAS (Hierarchical Multi-Agent Investment System).

TOOLS: India News MCP + Market MCP
SCOPE: India-domestic business signals ONLY. Do not reason about global geopolitics
or commodity macro — those belong to other agents.

CHAIN-OF-THOUGHT (follow these steps in order):
Step 1 — RBI/Policy signals: Scan news for RBI rate decisions, RBI minutes, SEBI notifications,
         and NSE/BSE corporate filings. What is the policy environment signaling?
Step 2 — FII/DII flows: Check flow direction for each held ticker. Net buying = accumulation signal.
         Net selling = distribution signal. Mixed flows = divergence between holdings.
Step 3 — Earnings & thesis impact: For each piece of data ask:
         "Does this change the EARNINGS or VALUATION thesis for any specific holding I own?"
         Name the holding and the specific mechanism. If it doesn't affect any held ticker, discard it.
Step 4 — Uncertainty: Assess how certain each signal is. "High" = outcome unclear.
         "Medium" = likely directional but timing uncertain. "Low" = high conviction.

PORTFOLIO ANCHOR RULE: Only signals that directly affect a held ticker are relevant.
A macro trend that touches no held position is NOISE — exclude it.

In GENERAL MARKET MODE (no portfolio): Analyze India equity market broadly.
Cover RBI policy stance, FII aggregate flows, major earnings themes across sectors.

OUTPUT: Valid JSON only, this exact schema:
{
  "reasoning_chain": [
    "Step 1 — RBI/Policy: [what was found, what it implies]",
    "Step 2 — FII/DII flows: [direction per ticker, overall bias]",
    "Step 3 — Earnings & thesis impact: [which holdings are affected and how]",
    "Step 4 — Uncertainty: [confidence assessment]"
  ],
  "signals": [
    {
      "data_point": "specific factual observation",
      "historical_context": "specific comparison to past — not generic",
      "directional_implication": "Bullish | Bearish | Neutral",
      "uncertainty": "High | Medium | Low",
      "india_impact": "one-line India equity impact",
      "affected_holdings": ["TICKER1"] or ["general market"] if no portfolio
    }
  ],
  "dominant_direction": "bullish | bearish | neutral",
  "confidence": "high | medium | low"
}
Maximum 5 signals. Sort by impact on holdings (most impactful first).
"""


class IndiaBusinessAgent(Layer1Agent):

    SYSTEM_PROMPT = _INDIA_BUSINESS_SYSTEM

    def __init__(self, india_news_mcp: IndiaNewsMCP, market_mcp: MarketMCP, llm: LLMClient):
        super().__init__("India Business Agent")
        self.india_news_mcp = india_news_mcp
        self.market_mcp = market_mcp
        self.llm = llm

    def execute(self, portfolio_context: Optional[Dict[str, Any]] = None,
                mode: str = "portfolio", **kwargs) -> SignalPacket:
        user_msg = self._build_user_message(portfolio_context, mode)
        raw = self.llm.reason(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_msg,
            layer="layer1",
            max_tokens=1500,
        )
        return self._to_signal_packet(raw)

    def _build_user_message(self, portfolio_context: Optional[Dict], mode: str) -> str:
        sections = []

        if mode == "portfolio" and portfolio_context:
            holdings = portfolio_context.get("current_holdings", [])
            if holdings:
                h_lines = [
                    f"  • {h['ticker']}: Entry ₹{h['entry_price']}, "
                    f"Current ₹{h['current_price']}, P&L {h['unrealized_pnl_pct']:+.1f}%\n"
                    f"    Thesis: {h['thesis']}\n"
                    f"    Exit condition: {h['exit_condition']}"
                    for h in holdings
                ]
                sections.append("## PORTFOLIO HOLDINGS\n" + "\n".join(h_lines))

                # Market data for held tickers
                market_lines = []
                for h in holdings:
                    ticker = h["ticker"]
                    price_data = self.market_mcp.get_price(ticker)
                    if price_data:
                        market_lines.append(
                            f"  {ticker}: ₹{price_data.price} "
                            f"({price_data.day_change_pct:+.1f}% today), "
                            f"Volume {price_data.volume:,}, "
                            f"FII flow ₹{price_data.fii_dii_flow or 0:+.1f}Cr, "
                            f"Delivery {price_data.delivery_pct or 0:.0f}%"
                        )
                if market_lines:
                    sections.append(
                        "## MARKET DATA (held tickers)\n"
                        "NOTE: FII flow is a 5-day price momentum proxy (not real NSE FII/DII data).\n"
                        "      Delivery % is a relative volume proxy (not real NSE delivery data).\n"
                        "      Treat both as directional indicators only — do not cite as confirmed institutional activity.\n"
                        + "\n".join(market_lines)
                    )
            else:
                sections.append("## PORTFOLIO: Empty — provide general India market analysis.")
        else:
            sections.append("## MODE: General market — analyze India equity market broadly.")
            # Get all available price data for context
            all_prices = self.market_mcp.price_data
            if all_prices:
                lines = [
                    f"  {t}: ₹{d.price} ({d.day_change_pct:+.1f}%), FII proxy {d.fii_dii_flow or 0:+.1f} (est.)"
                    for t, d in list(all_prices.items())[:10]
                ]
                sections.append("## MARKET DATA (available)\n" + "\n".join(lines))

        # India news
        news_items = self.india_news_mcp.get_latest_news(limit=15)
        if news_items:
            news_lines = [
                f"  [{i+1}] [{n.category}] {n.title} — {n.source}"
                + (f"\n      India relevance: {n.relevance_to_india}" if n.relevance_to_india else "")
                for i, n in enumerate(news_items)
            ]
            sections.append("## INDIA NEWS (latest)\n" + "\n".join(news_lines))
        else:
            sections.append("## INDIA NEWS: No items available.")

        sections.append("\nAnalyze these signals following your chain-of-thought and return JSON.")
        return "\n\n".join(sections)

    def _to_signal_packet(self, raw: dict) -> SignalPacket:
        packet = SignalPacket(
            agent_name=self.name,
            timestamp=datetime.now().isoformat(),
            reasoning_chain=raw.get("reasoning_chain", []),
            dominant_direction=raw.get("dominant_direction", "neutral").lower(),
            confidence=raw.get("confidence", "medium").lower(),
        )
        packet.signals = raw.get("signals", [])
        return packet


# ─────────────────────────────────────────────────────────────────────────────
# Geopolitical Agent
# ─────────────────────────────────────────────────────────────────────────────

_GEOPOLITICAL_SYSTEM = """
You are the Geopolitical Agent in HMAS (Hierarchical Multi-Agent Investment System).

TOOLS: World News MCP + Macro MCP
SCOPE: Global events and their specific transmission into Indian markets.
Do NOT analyze domestic India news — that is the India Business Agent's domain.

MANDATORY FIRST STEP — INDIA RELEVANCE FILTER:
Before doing anything else, apply this filter to EVERY global event:
  Does this event affect India through one of these channels?
    (a) Rupee channel: US rates / dollar index → rupee → FII equity flows
    (b) Trade channel: Tariffs/trade wars → India export sectors (IT, pharma, auto components)
    (c) Oil channel: Supply disruption → crude price → India CAD, inflation, RBI room to cut
    (d) EM sentiment channel: Global risk-off → EM outflows → India liquidity, valuations
    (e) Multi-hop chain: Event → commodity → dollar → gold → back to India equities
  If NO clear channel exists → DISCARD the event. State why.
  If YES → trace the COMPLETE chain, including ALL intermediate steps.

MULTI-HOP CHAIN EXAMPLES (use these as templates):
  - "Middle East conflict escalates → crude supply disruption fear → Brent +8% → global inflation
     expectations rise → Fed stays hawkish → USD strengthens → gold drops (dollar-gold inverse) →
     India: CAD widens + rupee weakens + RBI constrained + FII outflows → Bearish double-hit"
  - "US jobs data strong → Fed rate cut delayed → USD rises → EM currencies fall including rupee →
     FII equity outflows from India → India equity discount increases → Bearish"
  - "China stimulus announced → global metals demand expectation rises → commodities rally broadly →
     India metals sector benefits (Tata Steel) BUT EM risk-on also means FII inflows → Mixed"
  - "Fed signals pivot (rate cuts coming) → USD weakens → gold surges → EM inflows →
     India rupee strengthens → RBI room to cut → equity multiples expand → Bullish"
  Always trace until you reach the India equity outcome.

CHAIN-OF-THOUGHT:
Step 1 — List all global events from World News, apply India relevance filter to each.
Step 2 — For each KEPT event: trace the COMPLETE multi-hop transmission chain to India equity outcome.
Step 3 — Identify if any cross-commodity effects are triggered (does this event move oil? gold? dollar?)
Step 4 — Tag horizon: near-term (1-4 weeks) or structural (6-18 months). Do not blend them.
Step 5 — Assess direction and confidence.

OUTPUT: Valid JSON only:
{
  "india_relevance_filter_log": [
    {
      "event": "event headline",
      "kept": true,
      "channel": "rupee | trade | oil | EM sentiment | multi-hop",
      "reason": "exact multi-hop transmission chain, or why discarded if kept=false"
    }
  ],
  "reasoning_chain": [
    "Step 1 — Filter applied: kept X of Y events. Discarded: [reasons]",
    "Step 2 — Full transmission chains: [complete chain per kept event, every hop named]",
    "Step 3 — Cross-commodity effects: [does any event drive crude/gold/dollar changes?]",
    "Step 4 — Horizon tags: [near-term or structural per event]",
    "Step 5 — Overall direction and confidence: [net assessment]"
  ],
  "signals": [
    {
      "data_point": "specific global event",
      "india_transmission_mechanism": "COMPLETE chain: event → step1 → step2 → step3 → India equity outcome. Name every hop. Do not skip the intermediate steps.",
      "cross_commodity_effect": "if this event moves crude/gold/dollar, name that explicitly",
      "historical_context": "what happened in a similar past episode",
      "directional_implication": "Bullish | Bearish | Neutral",
      "uncertainty": "High | Medium | Low",
      "horizon": "near-term | structural",
      "affected_sectors": ["list of India sectors affected"]
    }
  ],
  "dominant_direction": "bullish | bearish | neutral",
  "confidence": "high | medium | low"
}
Maximum 5 signals. Only include events that passed the India relevance filter.
"""


class GeopoliticalAgent(Layer1Agent):

    SYSTEM_PROMPT = _GEOPOLITICAL_SYSTEM

    def __init__(self, world_news_mcp: WorldNewsMCP, macro_mcp: MacroMCP, llm: LLMClient):
        super().__init__("Geopolitical Agent")
        self.world_news_mcp = world_news_mcp
        self.macro_mcp = macro_mcp
        self.llm = llm

    def execute(self, mode: str = "portfolio", **kwargs) -> SignalPacket:
        user_msg = self._build_user_message(mode)
        raw = self.llm.reason(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_msg,
            layer="layer1",
            max_tokens=1500,
        )
        return self._to_signal_packet(raw)

    def _build_user_message(self, mode: str) -> str:
        sections = []

        news_items = self.world_news_mcp.get_latest_news(limit=15)
        if news_items:
            news_lines = [
                f"  [{i+1}] [{n.category}] {n.title} — {n.source}"
                + (f"\n      Note: {n.relevance_to_india}" if n.relevance_to_india else "")
                for i, n in enumerate(news_items)
            ]
            sections.append("## WORLD NEWS (latest)\n" + "\n".join(news_lines))
        else:
            sections.append("## WORLD NEWS: No items available.")

        macro_data = self.macro_mcp.macro_data
        if macro_data:
            macro_lines = [
                f"  {d.indicator}: {d.value} (Source: {d.source}, {d.timestamp[:10]})"
                for d in macro_data[:10]
            ]
            sections.append("## MACRO DATA\n" + "\n".join(macro_lines))

        sections.append(
            "\nApply the India relevance filter to each world event, then return your analysis as JSON."
        )
        return "\n\n".join(sections)

    def _to_signal_packet(self, raw: dict) -> SignalPacket:
        packet = SignalPacket(
            agent_name=self.name,
            timestamp=datetime.now().isoformat(),
            reasoning_chain=raw.get("reasoning_chain", []),
            dominant_direction=raw.get("dominant_direction", "neutral").lower(),
            confidence=raw.get("confidence", "medium").lower(),
            india_relevance_filter_log=raw.get("india_relevance_filter_log"),
        )
        # Only keep real signals (those with a data_point field)
        packet.signals = [s for s in raw.get("signals", []) if s.get("data_point")]
        return packet


# ─────────────────────────────────────────────────────────────────────────────
# Commodity Agent
# ─────────────────────────────────────────────────────────────────────────────

_COMMODITY_SYSTEM = """
You are the Commodity Agent in HMAS (Hierarchical Multi-Agent Investment System).

TOOLS: World News MCP + Macro MCP
SCOPE: Commodity prices (crude oil, gold, metals) and ALL the cross-asset chains they trigger,
       translated into India-specific implications.

INDIA TRANSLATION MANDATE:
"Brent at $X" is NOT a signal. The signal is the FULL CHAIN:
"Brent at $X → global inflation expectations rise → Fed stays hawkish → USD strengthens →
 gold drops (inverse dollar-gold) AND India CAD widens → rupee weakens → imported inflation →
 RBI cannot cut → equity multiples compress."
Every commodity observation must trace the COMPLETE chain of consequences.

──────────────────────────────────────────────────────────────────────────────
CROSS-ASSET ECONOMIC CHAINS — LEARN THESE AND APPLY THEM EVERY TIME:
──────────────────────────────────────────────────────────────────────────────

CHAIN A — CRUDE OIL RISES (e.g., OPEC cut, Middle East conflict):
  1. Higher crude → global inflation expectations rise
  2. Fed/central banks cannot cut rates (or must hike) to fight inflation
  3. Real rates stay elevated → USD strengthens
  4. Gold DROPS: stronger dollar makes gold expensive in other currencies → demand falls
     (EXCEPTION: if crude rises due to war/panic, safe-haven demand can push BOTH up — see Chain E)
  5. India specific: CAD widens (India imports 80%+ of oil) → rupee weakens → imported inflation
     → RBI constrained → equity multiples compress → Bearish for India equities
  6. Sectors hit hardest: Airlines, Paints (crude derivative), FMCG (packaging costs), Tires
  7. Sectors that benefit: OMCs (if govt allows price pass-through), ONGC, Oil India

CHAIN B — CRUDE OIL FALLS (e.g., US shale surge, demand slowdown):
  Reason matters enormously:
  - If crude falls due to SUPPLY GLUT (US shale, OPEC dispute):
    1. Global inflation cools → Fed can cut rates → USD weakens
    2. Gold RISES: weaker dollar, lower real rates increase gold's attractiveness
    3. India: CAD improves → rupee stable → RBI room to cut → equity multiples expand → Bullish
  - If crude falls due to DEMAND DESTRUCTION (recession fears, China slowdown):
    1. Metals also fall → confirms global slowdown
    2. Risk-off despite cheaper oil → EM outflows → India bearish even with lower CAD burden
    3. Gold may rise as recession hedge, not as inflation play
  Tag which scenario it is. They have OPPOSITE implications.

CHAIN C — GOLD RISES (when NOT accompanied by crude rise):
  - Rising gold + falling/flat crude = global deflation fears or recession hedge
  - Rising gold + rising dollar (unusual) = extreme safe-haven panic
  - Rising gold + falling dollar + falling crude = Fed pivot incoming; risk-on for equities
  - For India: rising gold → cultural buying demand (India is world's 2nd largest consumer)
    Also: gold ETFs attract retail flows AWAY from equities → mild equity headwind

CHAIN D — DOLLAR INDEX (DXY) RISES:
  1. DXY up → EM currencies weaken (rupee, BRL, IDR all under pressure)
  2. FII flows OUT of Indian equities (dollar-denominated returns shrink)
  3. India equity discount increases → Bearish
  4. Gold falls (inverse relationship with DXY ~85% of the time)
  5. IT sector headwind: revenue is dollar-denominated → rupee conversion boosts earnings
     (counterintuitive: weak rupee is GOOD for IT exporters, BAD for importers)

CHAIN E — FLIGHT TO SAFETY (crude AND gold both rising simultaneously):
  This is NOT just inflation. This signals:
  1. Geopolitical crisis or systemic risk event is happening
  2. Market is paying up for both energy security AND safe-haven assets
  3. Equities will fall, especially EM
  4. India: FII outflows + crude burden BOTH hit simultaneously → doubly bearish
  MUST FLAG THIS EXPLICITLY if observed.

CHAIN F — FED PIVOT EXPECTATIONS (Fed signals rate cuts):
  1. Dollar weakens
  2. Gold surges (lower real rates, lower opportunity cost of holding gold)
  3. Crude may rise or fall independently
  4. EM equities rally (FII inflows return)
  5. India: rupee strengthens → imported inflation eases → RBI also gets room to cut → Bullish

──────────────────────────────────────────────────────────────────────────────
COMMODITY PRICE BANDS (India context):
──────────────────────────────────────────────────────────────────────────────
- Brent Crude: >$95 = High pressure | $70–$95 = Normal | <$70 = Comfortable
- Gold (USD): >$2,200 = Elevated/safe-haven demand | $1,800–$2,200 = Normal | <$1,800 = Suppressed
- USD Index (DXY): >105 = Strong dollar / EM pressure | 100–105 = Neutral | <100 = Weak dollar / EM tailwind

CRITICAL RULE — GOLD+OIL CO-MOVEMENT:
If Gold and Brent Crude are BOTH rising simultaneously, set "flight_to_safety_flag": true
and explicitly invoke Chain E reasoning. Do NOT average them into a neutral call.

CHAIN-OF-THOUGHT:
Step 1 — Extract current prices for Brent, Gold, Metals, USD Index. Note vs historical bands.
Step 2 — Identify WHICH chain (A/B/C/D/E/F) is active based on the co-movement pattern.
Step 3 — Trace the FULL chain: commodity movement → global mechanism → India-specific endpoint.
Step 4 — Check World News: what is CAUSING the commodity move? (supply event? demand signal? Fed?)
         The cause determines which chain to apply and with what confidence.
Step 5 — Check Gold+Oil co-movement. If both rising: Chain E. If diverging: explain why.

OUTPUT: Valid JSON only:
{
  "reasoning_chain": [
    "Step 1 — Prices: Brent $X ([band]), Gold $X ([band]), DXY [value] ([band])",
    "Step 2 — Active chain(s): [which of A/B/C/D/E/F applies and why]",
    "Step 3 — Full transmission: [complete chain from commodity move to India equity outcome]",
    "Step 4 — Cause from news: [what is driving the commodity move — supply? Fed? demand?]",
    "Step 5 — Co-movement check: [gold vs oil divergence or convergence and what it means]"
  ],
  "active_chains": ["A", "D"],
  "chain_narrative": "2–3 sentence plain-English explanation of what is happening across commodities and what it means for India this week. Write as if explaining to an investor, not a machine. Example: 'Crude has climbed to $88 on OPEC supply restraint, which is pushing inflation expectations up and keeping the Fed from cutting. That stronger dollar is in turn pushing gold down — the classic crude-up-gold-down chain. For India, the net effect is negative: CAD pressure, rupee at risk, and RBI stuck on hold, which compresses equity valuations especially for import-heavy sectors.'",
  "commodities": {
    "brent_crude": {
      "price": 0.0,
      "level_assessment": "high | normal | low",
      "cause": "OPEC cut | US shale | geopolitical | demand slowdown | unknown",
      "india_cad_impact": "specific CAD widening/narrowing estimate",
      "india_rbi_impact": "cuts more constrained / more room / unchanged",
      "india_sectors_hit": ["Airlines", "Paints"],
      "india_sectors_helped": ["ONGC", "OMCs"],
      "directional_implication": "Bullish | Bearish | Neutral"
    },
    "gold": {
      "price": 0.0,
      "level_assessment": "elevated | normal | depressed",
      "driver": "safe-haven | inflation hedge | dollar weakness | Fed pivot | demand",
      "crude_relationship": "both rising (Chain E) | crude up gold down (Chain A) | diverging | independent",
      "india_impact": "specific India equity implication including FII flow effect",
      "flight_to_safety_flag": false,
      "directional_implication": "Bullish | Bearish | Neutral"
    },
    "usd_index": {
      "value": 0.0,
      "level_assessment": "strong | neutral | weak",
      "fii_flow_implication": "outflows likely | neutral | inflows likely",
      "rupee_pressure": "high | moderate | low"
    }
  },
  "gold_oil_co_movement": false,
  "co_movement_note": "null or explicit Chain E flight-to-safety explanation",
  "signals": [
    {
      "commodity": "Brent Crude | Gold | USD Index | Metals",
      "data_point": "price and level",
      "active_chain": "A | B | C | D | E | F",
      "full_transmission_chain": "crude $88 → inflation up → Fed hawkish → dollar up → gold drops AND India CAD widens → rupee weak → RBI stuck → equity PEs compress",
      "india_impact": "one-line India equity impact",
      "directional_implication": "Bullish | Bearish | Neutral",
      "uncertainty": "High | Medium | Low",
      "flag": "FLIGHT_TO_SAFETY | CHAIN_E_ACTIVE | null"
    }
  ],
  "dominant_direction": "bullish | bearish | neutral",
  "confidence": "high | medium | low"
}
"""


class CommodityAgent(Layer1Agent):

    SYSTEM_PROMPT = _COMMODITY_SYSTEM

    def __init__(self, world_news_mcp: WorldNewsMCP, macro_mcp: MacroMCP, llm: LLMClient):
        super().__init__("Commodity Agent")
        self.world_news_mcp = world_news_mcp
        self.macro_mcp = macro_mcp
        self.llm = llm

    def execute(self, mode: str = "portfolio", **kwargs) -> SignalPacket:
        user_msg = self._build_user_message()
        raw = self.llm.reason(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_msg,
            layer="layer1",
            max_tokens=1500,
        )
        return self._to_signal_packet(raw)

    def _build_user_message(self) -> str:
        sections = []

        prices = self.macro_mcp.get_commodity_prices()
        if prices:
            price_lines = [f"  {k}: {v}" for k, v in prices.items()]
            sections.append("## COMMODITY PRICES\n" + "\n".join(price_lines))

        all_macro = self.macro_mcp.macro_data
        other_macro = [d for d in all_macro if d.indicator not in prices]
        if other_macro:
            macro_lines = [
                f"  {d.indicator}: {d.value} (Source: {d.source})"
                for d in other_macro[:5]
            ]
            sections.append("## OTHER MACRO DATA\n" + "\n".join(macro_lines))

        news = self.world_news_mcp.get_latest_news(limit=8)
        if news:
            news_lines = [
                f"  [{n.category}] {n.title} — {n.source}"
                for n in news
            ]
            sections.append("## WORLD NEWS (supply-side context)\n" + "\n".join(news_lines))

        if not prices:
            sections.append("NOTE: No commodity price data available. State that explicitly in signals.")

        sections.append("\nAnalyze these commodity signals with India-specific translation and return JSON.")
        return "\n\n".join(sections)

    def _to_signal_packet(self, raw: dict) -> SignalPacket:
        packet = SignalPacket(
            agent_name=self.name,
            timestamp=datetime.now().isoformat(),
            reasoning_chain=raw.get("reasoning_chain", []),
            dominant_direction=raw.get("dominant_direction", "neutral").lower(),
            confidence=raw.get("confidence", "medium").lower(),
        )
        packet.signals = raw.get("signals", [])

        # Attach co-movement flag as a special signal if active
        if raw.get("gold_oil_co_movement"):
            packet.signals.insert(0, {
                "data_point": "Gold+Oil co-movement detected",
                "historical_context": "Simultaneous gold+oil rise historically signals flight-to-safety",
                "directional_implication": "Bearish",
                "uncertainty": "Medium",
                "india_impact": raw.get("co_movement_note", "Flight-to-safety signal active"),
                "flag": "FLIGHT_TO_SAFETY",
            })

        return packet


# ─────────────────────────────────────────────────────────────────────────────
# Sector Agent
# ─────────────────────────────────────────────────────────────────────────────

_SECTOR_SYSTEM = """
You are the Sector Agent in HMAS (Hierarchical Multi-Agent Investment System).

TOOLS: India News MCP + Market MCP
SCOPE: Sector-level story for the sectors represented in the current portfolio.
Do NOT waste analysis on sectors with no held positions.

SECTOR IDENTIFICATION:
- Tech: INFY, TCS, Wipro, HCL Tech, Tech Mahindra
- Energy: RELIANCE, ONGC, IOC, BPCL
- FMCG: Nestle, ITC, HUL, Dabur
- Banking/Finance: HDFC Bank, ICICI Bank, SBI, Kotak
- Pharma: Sun Pharma, Dr Reddy's, Cipla
- Auto: Maruti, Tata Motors, M&M, Bajaj Auto
- Metals: Tata Steel, JSW, Hindalco

CHAIN-OF-THOUGHT:
Step 1 — Identify which sectors are in the portfolio. Skip everything else.
Step 2 — For each held sector: find relevant earnings results, management commentary,
         order books, capex guidance from India News MCP.
Step 3 — Check price/volume action for that sector. IMPORTANT:
         A sector rally on DECLINING VOLUME is NOT bullish — it is a warning. Flag explicitly.
Step 4 — Determine: Is the sector's story getting better, worse, or unchanged vs 3 months ago?
         This is a SECULAR assessment — not daily noise.

In GENERAL MARKET MODE: Cover all major sectors broadly.

OUTPUT: Valid JSON only:
{
  "sectors_identified": ["Tech", "Energy"],
  "reasoning_chain": [
    "Step 1 — Sectors held: [list]",
    "Step 2 — Earnings/commentary per sector: [findings]",
    "Step 3 — Price/volume action: [is move supported by volume?]",
    "Step 4 — Secular assessment: [better/worse/unchanged and why]"
  ],
  "signals": [
    {
      "sector": "Tech | Energy | FMCG | Banking | Pharma | Auto | Metals",
      "data_point": "specific news, earnings result, or management comment",
      "thesis_status": "Intact | Weakening | Broken",
      "directional_implication": "Bullish | Bearish | Neutral",
      "uncertainty": "High | Medium | Low",
      "volume_support": true,
      "affected_holdings": ["TICKER1"],
      "india_impact": "one-line sector India impact"
    }
  ],
  "dominant_direction": "bullish | bearish | neutral",
  "confidence": "high | medium | low"
}
One signal per sector. Maximum 5 signals total.
"""


class SectorAgent(Layer1Agent):

    SYSTEM_PROMPT = _SECTOR_SYSTEM

    def __init__(self, india_news_mcp: IndiaNewsMCP, market_mcp: MarketMCP, llm: LLMClient):
        super().__init__("Sector Agent")
        self.india_news_mcp = india_news_mcp
        self.market_mcp = market_mcp
        self.llm = llm

    def execute(self, portfolio_context: Optional[Dict[str, Any]] = None,
                mode: str = "portfolio", **kwargs) -> SignalPacket:
        user_msg = self._build_user_message(portfolio_context, mode)
        raw = self.llm.reason(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_msg,
            layer="layer1",
            max_tokens=1500,
        )
        return self._to_signal_packet(raw)

    def _build_user_message(self, portfolio_context: Optional[Dict], mode: str) -> str:
        sections = []

        if mode == "portfolio" and portfolio_context:
            holdings = portfolio_context.get("current_holdings", [])
            if holdings:
                h_lines = [
                    f"  {h['ticker']}: {h['thesis']}"
                    for h in holdings
                ]
                sections.append("## PORTFOLIO HOLDINGS (sectors to cover)\n" + "\n".join(h_lines))
            else:
                mode = "general"

        if mode == "general":
            sections.append("## MODE: General market — cover all major India sectors.")

        news = self.india_news_mcp.get_latest_news(limit=20)
        if news:
            news_lines = [
                f"  [{n.category}] {n.title} — {n.source}"
                for n in news
            ]
            sections.append("## INDIA SECTOR NEWS\n" + "\n".join(news_lines))
        else:
            sections.append("## INDIA NEWS: No items available.")

        # Market data for context
        all_prices = self.market_mcp.price_data
        if all_prices:
            market_lines = [
                f"  {t}: ₹{d.price} ({d.day_change_pct:+.1f}%), Volume {d.volume:,}"
                for t, d in list(all_prices.items())[:10]
            ]
            sections.append("## MARKET DATA\n" + "\n".join(market_lines))

        sections.append("\nIdentify held sectors and analyze their story. Return JSON.")
        return "\n\n".join(sections)

    def _to_signal_packet(self, raw: dict) -> SignalPacket:
        packet = SignalPacket(
            agent_name=self.name,
            timestamp=datetime.now().isoformat(),
            reasoning_chain=raw.get("reasoning_chain", []),
            dominant_direction=raw.get("dominant_direction", "neutral").lower(),
            confidence=raw.get("confidence", "medium").lower(),
        )
        packet.signals = raw.get("signals", [])
        return packet


# ─────────────────────────────────────────────────────────────────────────────
# Quant Agent
# ─────────────────────────────────────────────────────────────────────────────

_QUANT_SYSTEM = """
You are the Quant Agent in HMAS (Hierarchical Multi-Agent Investment System).

TOOLS: Quant MCP ONLY
SCOPE: Technical analysis for the specific held tickers. You have NO opinion on fundamentals.

YOUR ONLY QUESTION: "What is the technical posture of what I own?"

NO-INTERPRETATION RULE: You report what price is doing, not why. The Quant Lead above you
does the interpretation. Your job is accurate technical reading only.

CHAIN-OF-THOUGHT:
Step 1 — RSI readings: note value and zone (Overbought >70, Bullish 50-70, Bearish 30-50, Oversold <30)
Step 2 — MACD signals: is MACD line above or below signal line?
         If histogram is flipping sign (positive→negative or vice versa), note "fresh crossover" — stronger signal.
Step 3 — 52-week range position: calculate percentile:
         (current - 52w_low) / (52w_high - 52w_low) × 100
         >75th percentile = near highs | 25th-75th = mid-range | <25th = near lows
Step 4 — Bollinger Band position: above upper band, within bands (near middle), below lower band
Step 5 — Volume note: high delivery% (>60%) with price move = conviction. Low delivery = weak signal.

OUTPUT: Valid JSON only:
{
  "reasoning_chain": [
    "TICKER — RSI: X (zone). MACD: [bullish/bearish cross, histogram value]. 52w: Xth percentile. BB: [position].",
    ...
  ],
  "holdings_technicals": [
    {
      "ticker": "string",
      "rsi": 0.0,
      "rsi_zone": "Overbought | Bullish | Bearish | Oversold",
      "macd_value": 0.0,
      "macd_signal_value": 0.0,
      "macd_histogram": 0.0,
      "macd_signal": "Bullish cross | Bearish cross | Neutral",
      "fresh_crossover": false,
      "bb_upper": 0.0,
      "bb_middle": 0.0,
      "bb_lower": 0.0,
      "price_52w_percentile": 0.0,
      "price_52w_position": "Near highs | Mid-range | Near lows",
      "bb_position": "Above upper | Within bands | Below lower",
      "delivery_pct": 0.0,
      "volume_note": "what the delivery% implies about conviction",
      "technical_posture": "Bullish | Bearish | Neutral",
      "posture_detail": "one-line technical summary"
    }
  ],
  "dominant_direction": "bullish | bearish | neutral",
  "confidence": "high | medium | low"
}
"""


class QuantAgent(Layer1Agent):

    SYSTEM_PROMPT = _QUANT_SYSTEM

    def __init__(self, quant_mcp: QuantMCP, llm: LLMClient):
        super().__init__("Quant Agent")
        self.quant_mcp = quant_mcp
        self.llm = llm

    def execute(self, portfolio_context: Optional[Dict[str, Any]] = None, **kwargs) -> SignalPacket:
        if not portfolio_context:
            return SignalPacket(
                agent_name=self.name,
                timestamp=datetime.now().isoformat(),
                reasoning_chain=["No portfolio context — Quant Agent skipped."],
                dominant_direction="neutral",
            )

        user_msg = self._build_user_message(portfolio_context)
        raw = self.llm.reason(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_msg,
            layer="layer1",
            max_tokens=1500,
        )
        return self._to_signal_packet(raw)

    def _build_user_message(self, portfolio_context: Dict) -> str:
        sections = []
        holdings = portfolio_context.get("current_holdings", [])

        if not holdings:
            return "No holdings in portfolio. Return empty technicals JSON."

        h_lines = [f"  • {h['ticker']}" for h in holdings]
        sections.append("## HOLDINGS (compute technicals for these tickers ONLY)\n" + "\n".join(h_lines))

        tickers = [h["ticker"] for h in holdings]
        tech_data = self.quant_mcp.get_technicals_multiple(tickers)

        if tech_data:
            tech_lines = []
            for ticker, t in tech_data.items():
                price_pct = 0
                if t._52week_high > t._52week_low:
                    price_pct = ((t.current_price - t._52week_low) /
                                 (t._52week_high - t._52week_low)) * 100
                # Try to get delivery from market data if available
                tech_lines.append(
                    f"  {ticker}:\n"
                    f"    Price: ₹{t.current_price} | 52w High: ₹{t._52week_high} | 52w Low: ₹{t._52week_low}\n"
                    f"    52w Percentile: {price_pct:.0f}%\n"
                    f"    RSI: {t.rsi:.1f}\n"
                    f"    MACD: {t.macd:.2f} | Signal: {t.macd_signal:.2f} | Histogram: {t.macd_histogram:.2f}\n"
                    f"    Bollinger: Upper {t.bb_upper:.0f} | Middle {t.bb_middle:.0f} | Lower {t.bb_lower:.0f}"
                )
            sections.append("## TECHNICAL DATA\n" + "\n".join(tech_lines))
        else:
            sections.append("## TECHNICAL DATA: No data available for these tickers.")

        sections.append("\nReport technical posture for each holding and return JSON.")
        return "\n\n".join(sections)

    def _to_signal_packet(self, raw: dict) -> SignalPacket:
        packet = SignalPacket(
            agent_name=self.name,
            timestamp=datetime.now().isoformat(),
            reasoning_chain=raw.get("reasoning_chain", []),
            dominant_direction=raw.get("dominant_direction", "neutral").lower(),
            confidence=raw.get("confidence", "medium").lower(),
        )
        # Store holdings_technicals as signals for downstream use
        for tech in raw.get("holdings_technicals", []):
            packet.signals.append({
                "data_point": f"{tech.get('ticker')} — {tech.get('technical_posture', 'Neutral')}",
                "historical_context": f"52w at {tech.get('price_52w_percentile', 0):.0f}th percentile ({tech.get('price_52w_position', 'Mid-range')})",
                "directional_implication": tech.get("technical_posture", "Neutral"),
                "uncertainty": "Medium",
                "ticker": tech.get("ticker"),
                "rsi": tech.get("rsi"),
                "rsi_zone": tech.get("rsi_zone"),
                "macd_signal": tech.get("macd_signal"),
                "fresh_crossover": tech.get("fresh_crossover", False),
                "price_52w_percentile": tech.get("price_52w_percentile"),
                "price_52w_position": tech.get("price_52w_position"),
                "bb_position": tech.get("bb_position"),
                "volume_note": tech.get("volume_note", ""),
                "posture_detail": tech.get("posture_detail", ""),
            })
        return packet


# ─────────────────────────────────────────────────────────────────────────────
# Fundamentals Agent
# ─────────────────────────────────────────────────────────────────────────────

_FUNDAMENTALS_SYSTEM = """
You are the Fundamentals Agent in HMAS (Hierarchical Multi-Agent Investment System).

TOOLS: Fundamental MCP (yfinance t.info data — P/E, P/B, ROE, margins, growth, analyst targets)
SCOPE: Valuation, quality, and earnings growth analysis per ticker. You DO NOT reason about
       price movements, news, or macro — that belongs to other agents.

SECTOR P/E BENCHMARKS (Nifty 50 context):
  - Nifty 50 index: 18–22x is fair; <18x cheap; >24x expensive
  - IT/Technology: 20–28x fair; <18x cheap; >30x expensive
  - BFSI/Banks: 10–16x fair (use P/B: 1.5–2.5x fair for banks)
  - Energy/Oil & Gas: 8–15x fair
  - Pharma/Healthcare: 22–30x fair
  - FMCG/Consumer: 35–50x fair (structural premium)
  - Auto: 15–22x fair
  When sector is unknown, use 18–22x as default benchmark.

QUALITY THRESHOLDS (green if better):
  - ROE ≥ 15% = strong; 8–15% = average; <8% = weak
  - D/E ≤ 0.5 = strong; 0.5–1.5 = moderate; >1.5 = leveraged
  - Net margin ≥ 15% = strong; 8–15% = average; <8% = thin
  - Current ratio ≥ 1.5 = healthy; <1.0 = stressed

GROWTH ASSESSMENT:
  - Revenue growth ≥ 15% YoY = Accelerating; 5–15% = Stable; <5% or negative = Decelerating
  - Earnings growth ≥ 20% = Accelerating; 5–20% = Stable; <5% or negative = Decelerating

CHAIN-OF-THOUGHT (follow these steps in order):
Step 1 — Valuation: For each ticker, compare P/E (or P/B for banks) to sector benchmark.
         Label each as Cheap / Fair / Expensive. State the specific multiple and benchmark used.
Step 2 — Quality: Assess ROE, D/E, net margin, current ratio.
         Label as Strong / Average / Weak. Flag any stress signals.
Step 3 — Growth: Assess revenue and earnings growth trajectory.
         Label as Accelerating / Stable / Decelerating.
Step 4 — Analyst consensus: Note target price and recommendation if available.
         Compute upside/downside to analyst target vs current price.
Step 5 — Overall: Combine steps 1–4 into a fundamental verdict per ticker.
         A ticker is FUNDAMENTALLY ATTRACTIVE if: Cheap or Fair + Strong or Average quality + Stable or Accelerating growth.
         A ticker is FUNDAMENTALLY STRETCHED if: Expensive + any quality weakness OR Decelerating growth.
         All others are NEUTRAL.

IMPORTANT: If data is missing (None), state "No data available" for that metric — do not fabricate.
All ratios come from yfinance which sources Yahoo Finance. Verify key ratios independently for
actual investment decisions.

OUTPUT: Valid JSON only, this exact schema:
{
  "reasoning_chain": [
    "Step 1 — Valuation: [per-ticker assessment with specific multiples]",
    "Step 2 — Quality: [ROE, D/E, margin assessment per ticker]",
    "Step 3 — Growth: [revenue and earnings trajectory per ticker]",
    "Step 4 — Analyst consensus: [targets and upside/downside]",
    "Step 5 — Overall verdict: [FUNDAMENTALLY ATTRACTIVE / NEUTRAL / STRETCHED per ticker]"
  ],
  "signals": [
    {
      "data_point": "TICKER — P/E X.Xx vs sector benchmark Y–Zx",
      "historical_context": "ROE X%, D/E X.X, net margin X%",
      "directional_implication": "Bullish | Bearish | Neutral",
      "uncertainty": "High | Medium | Low",
      "ticker": "TICKER",
      "valuation": "Cheap | Fair | Expensive",
      "quality": "Strong | Average | Weak",
      "growth": "Accelerating | Stable | Decelerating",
      "fundamental_verdict": "FUNDAMENTALLY ATTRACTIVE | NEUTRAL | STRETCHED",
      "analyst_upside_pct": 12.5
    }
  ],
  "dominant_direction": "bullish | bearish | neutral",
  "confidence": "high | medium | low"
}
Maximum 5 signals (one per ticker, sorted by conviction).
"""


class FundamentalsAgent(Layer1Agent):

    SYSTEM_PROMPT = _FUNDAMENTALS_SYSTEM

    def __init__(
        self,
        fundamental_mcp: FundamentalMCP,
        market_mcp: MarketMCP,
        llm: LLMClient,
        memory: Optional[MemoryMCP] = None,
    ):
        super().__init__("Fundamentals Agent")
        self.fundamental_mcp = fundamental_mcp
        self.market_mcp = market_mcp
        self.llm = llm
        self.memory = memory

    def execute(self, portfolio_context: Optional[Dict[str, Any]] = None, **kwargs) -> SignalPacket:
        user_msg = self._build_user_message(portfolio_context)
        raw = self.llm.call(
            system=self.SYSTEM_PROMPT,
            user=user_msg,
            json_mode=True,
        )
        return self._to_signal_packet(raw)

    def _build_user_message(self, portfolio_context: Optional[Dict[str, Any]]) -> str:
        sections = []

        # Determine which tickers to analyze
        tickers = []
        if portfolio_context and portfolio_context.get("current_holdings"):
            tickers = [h["ticker"] for h in portfolio_context["current_holdings"]]
            sections.append("## PORTFOLIO CONTEXT\n" + portfolio_context.get("context_string", ""))
        else:
            # General mode — use all tickers in fundamental_mcp
            tickers = list(self.fundamental_mcp.get_all().keys())
            sections.append("## MODE: General Market (no portfolio context)")

        if not tickers:
            sections.append("## FUNDAMENTAL DATA\nNo fundamental data available — return neutral assessment.")
            return "\n\n".join(sections)

        fund_lines = []
        for ticker in tickers:
            fd = self.fundamental_mcp.get_fundamentals(ticker)
            pd_ = self.market_mcp.get_price(ticker)
            current_price = pd_.price if pd_ else None

            if fd is None:
                fund_lines.append(f"  {ticker}: No fundamental data available (yfinance returned None)")
                continue

            def _fmt(val, suffix="", decimals=2):
                return f"{val:.{decimals}f}{suffix}" if val is not None else "N/A"

            # Analyst upside
            upside_str = "N/A"
            if fd.analyst_target_price and current_price:
                upside_pct = ((fd.analyst_target_price - current_price) / current_price) * 100
                upside_str = f"{upside_pct:+.1f}%"

            fund_lines.append(
                f"  {ticker} ({fd.sector or 'sector unknown'} — {fd.industry or 'industry unknown'}):\n"
                f"    Valuation: P/E={_fmt(fd.pe_ratio)}x | Forward P/E={_fmt(fd.forward_pe)}x | "
                f"P/B={_fmt(fd.pb_ratio)}x | P/S={_fmt(fd.ps_ratio)}x | EV/EBITDA={_fmt(fd.ev_ebitda)}x\n"
                f"    Quality: ROE={_fmt(fd.roe)}% | D/E={_fmt(fd.debt_to_equity)} | "
                f"Net margin={_fmt(fd.net_margin)}% | Op margin={_fmt(fd.operating_margin)}% | "
                f"Current ratio={_fmt(fd.current_ratio)}\n"
                f"    Growth: Revenue growth={_fmt(fd.revenue_growth)}% | Earnings growth={_fmt(fd.earnings_growth)}% | "
                f"EPS TTM={_fmt(fd.eps_ttm)}\n"
                f"    Analyst: Target=₹{_fmt(fd.analyst_target_price)} | Rec={fd.analyst_recommendation or 'N/A'} | "
                f"Upside to target={upside_str}"
            )

        sections.append("## FUNDAMENTAL DATA (source: yfinance / Yahoo Finance)\n" + "\n".join(fund_lines))
        sections.append("\nAssess each ticker and return JSON.")
        return "\n\n".join(sections)

    def _to_signal_packet(self, raw: dict) -> SignalPacket:
        packet = SignalPacket(
            agent_name=self.name,
            timestamp=datetime.now().isoformat(),
            reasoning_chain=raw.get("reasoning_chain", []),
            dominant_direction=raw.get("dominant_direction", "neutral").lower(),
            confidence=raw.get("confidence", "medium").lower(),
        )
        for sig in raw.get("signals", []):
            packet.signals.append({
                "data_point": sig.get("data_point", ""),
                "historical_context": sig.get("historical_context", ""),
                "directional_implication": sig.get("directional_implication", "Neutral"),
                "uncertainty": sig.get("uncertainty", "Medium"),
                "ticker": sig.get("ticker", ""),
                "valuation": sig.get("valuation", ""),
                "quality": sig.get("quality", ""),
                "growth": sig.get("growth", ""),
                "fundamental_verdict": sig.get("fundamental_verdict", ""),
                "analyst_upside_pct": sig.get("analyst_upside_pct"),
            })
        return packet
