"""
HMAS Example — Hierarchical Multi-Agent Investment System

Demonstrates two modes:
  1. General market analysis  — no portfolio needed
  2. Portfolio-specific brief — per-holding guidance with full reasoning chain

Requirements:
  pip install -r requirements.txt
  export OPENAI_API_KEY=sk-...

Each mode calls real OpenAI models (gpt-4o-mini for L1, gpt-4o for L2, o3-mini for L3).
"""

from pathlib import Path
from datetime import datetime

from src.core.workflow import HMASWorkflow
from src.mcp_tools.mcp_tools import (
    india_news_mcp, world_news_mcp, market_mcp, quant_mcp, macro_mcp,
    NewsItem, PriceData, TechnicalData, MacroData,
)


# ─────────────────────────────────────────────────────────────────────────────
# Sample data population
# ─────────────────────────────────────────────────────────────────────────────

def populate_market_data():
    """Populate MCP tools with sample market data."""
    print("[DATA] Loading sample market data into MCP tools...")

    # ── India News ─────────────────────────────────────────────────────────
    india_news_mcp.add_news_item(NewsItem(
        title="RBI Keeps Rates Unchanged, Signals Accommodative Stance Ahead",
        source="Economic Times",
        timestamp=datetime.now().isoformat(),
        content="Reserve Bank of India held repo rate at 6.5% but governor signalled readiness to cut if inflation eases.",
        category="RBI Policy",
        relevance_to_india="Accommodative signal supports equity valuations via lower cost of capital expectations.",
    ))
    india_news_mcp.add_news_item(NewsItem(
        title="Reliance Industries Q3 Results: Jio ARPU at ₹182, Up 5% QoQ",
        source="Moneycontrol",
        timestamp=datetime.now().isoformat(),
        content="Reliance Industries reported strong Jio subscriber addition and ARPU improvement.",
        category="Earnings",
        relevance_to_india="Positive for RELIANCE.NS thesis — Jio ARPU growth intact.",
    ))
    india_news_mcp.add_news_item(NewsItem(
        title="Infosys Q3 Revenue Growth 4.2% in CC Terms; Attrition Falls to 12.9%",
        source="Business Standard",
        timestamp=datetime.now().isoformat(),
        content="Infosys narrowed FY25 guidance to upper end; deal wins strong at $2.1B TCV.",
        category="Earnings",
        relevance_to_india="Positive for INFY.NS thesis — attrition within threshold, guidance narrowed upward.",
    ))
    india_news_mcp.add_news_item(NewsItem(
        title="India FII Outflows: ₹8,200 Cr Sold in Equities This Week",
        source="NSE",
        timestamp=datetime.now().isoformat(),
        content="Foreign institutional investors continued selling amid dollar strength.",
        category="FII/DII Flows",
        relevance_to_india="Bearish near-term pressure; FII outflows typically precede short-term corrections.",
    ))

    # ── World News ─────────────────────────────────────────────────────────
    world_news_mcp.add_news_item(NewsItem(
        title="US Federal Reserve Holds Rates; Powell Signals 'Higher for Longer'",
        source="Reuters",
        timestamp=datetime.now().isoformat(),
        content="Fed keeps rates at 5.25-5.5%; dot plot suggests only 1 cut in 2025.",
        category="Fed Policy",
        relevance_to_india="Stronger dollar pressures rupee and FII equity flows into India.",
    ))
    world_news_mcp.add_news_item(NewsItem(
        title="OPEC+ Extends Production Cuts Through Q2 2025",
        source="Bloomberg",
        timestamp=datetime.now().isoformat(),
        content="Saudi Arabia and Russia lead decision to maintain 2.2 million bpd of voluntary cuts.",
        category="Commodity",
        relevance_to_india="Oil supply constraint supports prices above $75 — watch India CAD impact.",
    ))

    # ── Market Data ─────────────────────────────────────────────────────────
    market_mcp.set_price("RELIANCE.NS", PriceData(
        ticker="RELIANCE.NS",
        price=2210,
        volume=25_000_000,
        day_change_pct=0.5,
        _52week_high=2650,
        _52week_low=1980,
        fii_dii_flow=15.5,     # FII buying this stock specifically
        delivery_pct=62.5,
    ))
    market_mcp.set_price("INFY.NS", PriceData(
        ticker="INFY.NS",
        price=1850,
        volume=8_500_000,
        day_change_pct=-0.2,
        _52week_high=2100,
        _52week_low=1450,
        fii_dii_flow=-8.2,     # FII selling this stock
        delivery_pct=58.3,
    ))

    # ── Technical Data ─────────────────────────────────────────────────────
    quant_mcp.set_technicals("RELIANCE.NS", TechnicalData(
        ticker="RELIANCE.NS",
        rsi=58.3,
        macd=12.5,
        macd_signal=10.2,
        macd_histogram=2.3,     # Positive → bullish momentum
        bb_upper=2300,
        bb_middle=2180,
        bb_lower=2060,
        current_price=2210,
        _52week_high=2650,
        _52week_low=1980,
    ))
    quant_mcp.set_technicals("INFY.NS", TechnicalData(
        ticker="INFY.NS",
        rsi=42.1,
        macd=-5.2,
        macd_signal=-3.8,
        macd_histogram=-1.4,    # Negative → bearish momentum
        bb_upper=1920,
        bb_middle=1810,
        bb_lower=1700,
        current_price=1850,
        _52week_high=2100,
        _52week_low=1450,
    ))

    # ── Macro Data ─────────────────────────────────────────────────────────
    macro_mcp.add_data(MacroData(
        indicator="Brent Crude",
        value=78.5,
        timestamp=datetime.now().isoformat(),
        source="OPEC",
    ))
    macro_mcp.add_data(MacroData(
        indicator="Gold",
        value=2065.50,
        timestamp=datetime.now().isoformat(),
        source="London Metals Exchange",
    ))
    macro_mcp.add_data(MacroData(
        indicator="USD/INR",
        value=83.4,
        timestamp=datetime.now().isoformat(),
        source="RBI",
    ))

    print("[OK] Market data loaded.\n")


# ─────────────────────────────────────────────────────────────────────────────
# Mode 1: General Market Analysis (no portfolio required)
# ─────────────────────────────────────────────────────────────────────────────

def run_general_market_mode(workflow: HMASWorkflow):
    print("\n" + "=" * 80)
    print("MODE 1: GENERAL MARKET ANALYSIS")
    print("No portfolio context — clean market read for any India equity investor.")
    print("=" * 80 + "\n")

    result = workflow.run_full_cycle(
        triggers=["scheduled_weekly_review"],
        mode="general",
    )

    workflow.print_full_report(result, show_signal_trail=True)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Mode 2: Portfolio-Specific Analysis
# ─────────────────────────────────────────────────────────────────────────────

def setup_portfolio(workflow: HMASWorkflow):
    """Add holdings to portfolio memory."""
    print("[SETUP] Adding holdings to portfolio...")

    workflow.memory.add_holding(
        ticker="RELIANCE.NS",
        entry_price=2450,
        entry_date="2024-03-10",
        current_price=2210,
        unrealized_pnl_pct=-9.8,
        thesis="Energy transition + Jio ARPU growth; leadership in new energy sectors.",
        exit_condition="Jio ARPU growth stalls for 2 consecutive quarters OR crude sustained above $95.",
    )
    workflow.memory.add_holding(
        ticker="INFY.NS",
        entry_price=1920,
        entry_date="2024-02-15",
        current_price=1850,
        unrealized_pnl_pct=-3.6,
        thesis="IT services recovery with AI/cloud tailwinds; strong execution and deal wins.",
        exit_condition="Attrition exceeds 16% for 2 consecutive quarters OR deal TCV growth turns negative.",
    )

    print("[OK] Portfolio set up with 2 holdings.\n")


def run_portfolio_mode(workflow: HMASWorkflow):
    print("\n" + "=" * 80)
    print("MODE 2: PORTFOLIO-SPECIFIC BRIEF")
    print("Per-holding guidance: thesis validation, blank slate test, full reasoning chain.")
    print("=" * 80 + "\n")

    result = workflow.run_full_cycle(
        triggers=["scheduled_weekly_review"],
        mode="portfolio",
    )

    workflow.print_full_report(result, show_signal_trail=True)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # Initialize workflow — reads OPENAI_API_KEY from environment
    # Or pass: HMASWorkflow(api_key="sk-...", memory_file=Path("portfolio_memory.json"))
    workflow = HMASWorkflow(memory_file=Path("portfolio_memory.json"))

    # Populate sample market data into MCP tools
    populate_market_data()

    # ── Run both modes ────────────────────────────────────────────────────────
    # Mode 1: General market (no portfolio needed)
    run_general_market_mode(workflow)

    # Set up portfolio before portfolio mode
    setup_portfolio(workflow)

    # Mode 2: Portfolio-specific with full explainability
    run_portfolio_mode(workflow)

    print("\n[DONE] Portfolio memory saved to portfolio_memory.json")


if __name__ == "__main__":
    main()
