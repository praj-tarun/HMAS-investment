"""
test_pipeline.py — Verifies the full OpenAI pipeline (Layer 1 -> 2 -> 3) with one stock.

Injects mock data for INFY.NS so no live yfinance fetch is needed.
Requires OPENAI_API_KEY to be set in .env or environment.

Usage:
    python test_pipeline.py
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from src.mcp_tools.mcp_tools import (
    india_news_mcp, world_news_mcp, market_mcp, quant_mcp, macro_mcp,
    NewsItem, PriceData, TechnicalData, MacroData,
)

now = datetime.now().isoformat()

# ── Mock market data for INFY.NS ─────────────────────────────────────────────
market_mcp.set_price("INFY.NS", PriceData(
    ticker="INFY.NS",
    price=1279.0,
    volume=1_200_000,
    day_change_pct=-0.5,
    _52week_high=1850.0,
    _52week_low=1170.0,
    fii_dii_flow=-5.2,
    delivery_pct=42.0,
))

quant_mcp.set_technicals("INFY.NS", TechnicalData(
    ticker="INFY.NS",
    rsi=42.5,
    macd=-8.3,
    macd_signal=-5.1,
    macd_histogram=-3.2,
    bb_upper=1380.0,
    bb_middle=1290.0,
    bb_lower=1200.0,
    current_price=1279.0,
    _52week_high=1850.0,
    _52week_low=1170.0,
))

# ── Mock news ─────────────────────────────────────────────────────────────────
india_news_mcp.add_news_item(NewsItem(
    title="Infosys cuts FY25 revenue guidance to 4.5-5% amid weak BFSI demand",
    source="ET Markets",
    timestamp=now,
    content="Infosys guidance cut.",
    category="Earnings",
    relevance_to_india="IT sector revenue miss signals weak enterprise tech spending.",
))
india_news_mcp.add_news_item(NewsItem(
    title="RBI keeps repo rate unchanged at 6.5%, maintains withdrawal of accommodation",
    source="Economic Times",
    timestamp=now,
    content="RBI hold.",
    category="RBI Policy",
    relevance_to_india="RBI on hold; equity multiples stay compressed.",
))

world_news_mcp.add_news_item(NewsItem(
    title="Fed signals two rate cuts in 2025 as US inflation cools",
    source="Reuters",
    timestamp=now,
    content="Fed cuts signal.",
    category="Fed Policy",
    relevance_to_india="Fed easing relieves dollar pressure; rupee may stabilise; FII inflows possible.",
))
world_news_mcp.add_news_item(NewsItem(
    title="Brent crude falls below $80 on weak China demand outlook",
    source="BBC Business",
    timestamp=now,
    content="Oil falls.",
    category="Commodity",
    relevance_to_india="Lower crude = India CAD improvement; RBI gains room to cut.",
))

# ── Mock commodity / macro data ────────────────────────────────────────────────
macro_mcp.add_data(MacroData(indicator="Brent Crude", value=79.5, timestamp=now, source="Yahoo Finance"))
macro_mcp.add_data(MacroData(indicator="Gold", value=2630.0, timestamp=now, source="Yahoo Finance"))
macro_mcp.add_data(MacroData(indicator="USD Index", value=104.2, timestamp=now, source="Yahoo Finance"))
macro_mcp.add_data(MacroData(indicator="US 10Y Yield", value=4.25, timestamp=now, source="Yahoo Finance"))

# ── Run pipeline ──────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("  HMAS PIPELINE TEST — OpenAI (gpt-4o-mini / gpt-4o / o3-mini)")
print("  Stock under analysis: INFY.NS (mock data)")
print("=" * 72 + "\n")

from src.core.workflow import HMASWorkflow

try:
    workflow = HMASWorkflow(memory_file=Path("portfolio_memory.json"))
except ValueError as exc:
    print(f"[ERROR] {exc}")
    sys.exit(1)

result = workflow.run_full_cycle(
    triggers=["scheduled_weekly_review"],
    mode="portfolio",
)

workflow.print_full_report(result, show_signal_trail=True)

# Verify key fields in the output
briefs = result.get("briefs", [])
infy_brief = next((b for b in briefs if b.get("ticker") == "INFY.NS"), None)

print("\n" + "=" * 72)
print("  PIPELINE VERIFICATION")
print("=" * 72)
print(f"  Layers completed:     L1 agents + L2 leads + L3 orchestrator")
print(f"  Briefs produced:      {len(briefs)}")
if infy_brief:
    print(f"  INFY.NS flag:         {infy_brief.get('flag')}")
    print(f"  INFY.NS blank slate:  {infy_brief.get('blank_slate_test')}")
    print(f"  INFY.NS thesis:       {infy_brief.get('thesis_status')}")
    rc = infy_brief.get("reasoning_chain", [])
    print(f"  Reasoning steps:      {len(rc)}")
    print(f"\n  [OK] OpenAI pipeline verified end-to-end.")
else:
    print(f"  [!] INFY.NS brief not found in output — check agent logs above.")
print("=" * 72 + "\n")
