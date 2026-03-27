"""
run.py - HMAS Command-Line Interface for Indian Retail Investors

Usage:
    python run.py general              # General market analysis (no portfolio)
    python run.py portfolio            # Portfolio analysis with your holdings
    python run.py show                 # Show current portfolio (no API needed)
    python run.py add TICKER           # Interactively add/update a holding
    python run.py remove TICKER        # Remove a holding
    python run.py history              # Show decision history
    python run.py rbi                  # Quick RBI/Fed announcement analysis
    python run.py event geopolitical   # Quick geopolitical event analysis
    python run.py export               # Export last report to markdown file

    # Watchlist commands
    python run.py watch TICKER         # Add ticker to buy watchlist
    python run.py unwatch TICKER       # Remove ticker from watchlist
    python run.py watchlist            # Show current watchlist
    python run.py scan                 # Scan watchlist for buy opportunities (full analysis)

Flags:
    --no-live-data                     # Skip yfinance, use data already in MCPs
    --save                             # Save report to reports/YYYY-MM-DD_MODE.md
    --show-trail                       # Show full agent signal trail in output
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

from src.core.workflow import HMASWorkflow
from src.memory.memory_mcp import MemoryMCP


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

MEMORY_FILE = Path("portfolio_memory.json")
REPORTS_DIR = Path("reports")
LAST_REPORT_FILE = Path(".last_report.json")

# Shared report history (per-mode archive + previous context)
from src.core.report_history import ReportHistory
_report_history = ReportHistory()

W = 72  # Display width


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def load_memory() -> MemoryMCP:
    return MemoryMCP(MEMORY_FILE)


def check_api_key() -> bool:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or key == "sk-your-key-here":
        print("\n[ERROR] OPENAI_API_KEY is not set.")
        print("  Set it in .env file:   OPENAI_API_KEY=sk-...")
        print("  Or export it:          export OPENAI_API_KEY=sk-...")
        return False
    return True


def load_live_data(tickers: list, skip: bool = False) -> dict:
    """Load live market + news data. Returns summary or empty dict if skipped."""
    if skip:
        print("  [SKIP] Live data fetch skipped (--no-live-data)")
        return {}

    summary = {}

    # 1. Fetch market data + technicals via yfinance
    try:
        from src.data.market_fetcher import populate_mcps
        if tickers:
            print(f"\n[1/2] Fetching live market data for {len(tickers)} ticker(s)...")
            mkt_summary = populate_mcps(tickers)
            summary["market"] = mkt_summary
        else:
            print("[1/2] No tickers - fetching commodity/macro data only...")
            from src.data.market_fetcher import fetch_commodity_data
            from src.mcp_tools.mcp_tools import macro_mcp, MacroData
            commodities = fetch_commodity_data()
            for name, price in commodities.items():
                macro_mcp.add_data(MacroData(
                    indicator=name,
                    value=price,
                    timestamp=datetime.now().isoformat(),
                    source="Yahoo Finance",
                ))
    except ImportError:
        print("  [WARN] market_fetcher unavailable - skipping live prices")

    # 2. Fetch RSS news
    try:
        from src.data.news_fetcher import populate_news_mcps
        print("[2/2] Fetching India + world news from RSS feeds...")
        news_counts = populate_news_mcps()
        summary["news"] = news_counts
        print(f"      India news: {news_counts['india_items']} items | "
              f"World news: {news_counts['world_items']} items")
    except ImportError:
        print("  [WARN] news_fetcher unavailable - skipping RSS news")

    return summary


def print_analysis_header(tickers: list, news_summary: dict):
    """Print a summary of what data was loaded before analysis starts."""
    news = news_summary.get("news", {})
    india_n = news.get("india_items", 0)
    world_n = news.get("world_items", 0)
    n_tickers = len(tickers)
    total_news = india_n + world_n

    print(f"\n  Analyzing {n_tickers} holding(s) with {total_news} news items "
          f"({india_n} India, {world_n} world)")
    print()


def save_report(result: dict, mode: str) -> Path:
    """Save result to reports/ dir as markdown. Returns saved path."""
    from src.core.reporter import save_report as do_save
    return do_save(result, mode)


def save_last_report(result: dict):
    """Save the last result to .last_report.json and per-mode archive."""
    try:
        with open(LAST_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
    except Exception:
        pass
    # Also persist to per-mode archive for history + learning
    mode = result.get("mode", "")
    if "portfolio" in mode:
        try:
            _report_history.save("portfolio", result)
        except Exception:
            pass
    elif "scout" in mode:
        try:
            _report_history.save("scout", result)
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------

def cmd_show(args: list):
    """Show current portfolio holdings."""
    memory = load_memory()
    ctx = memory.get_portfolio_context()
    holdings = ctx["current_holdings"]

    print(f"\n{'=' * W}")
    print("  PORTFOLIO HOLDINGS")
    print(f"{'=' * W}")

    if not holdings:
        print("\n  Portfolio is empty.")
        print("  Add holdings with:  python run.py add TICKER.NS")
        print(f"\n{'=' * W}\n")
        return

    total_invested = 0.0
    total_current = 0.0

    for h in holdings:
        ticker = h["ticker"]
        entry = h["entry_price"]
        current = h["current_price"]
        pnl = h["unrealized_pnl_pct"]
        qty = h.get("quantity", 1.0)
        thesis = h["thesis"]
        exit_cond = h.get("exit_condition", "Not set")
        entry_date = h.get("entry_date", "")

        invested_val = entry * qty
        current_val = current * qty
        total_invested += invested_val
        total_current += current_val

        pnl_str = f"{pnl:+.1f}%"

        print()
        print(f"  {ticker}")
        print(f"  {'Entry':12} Rs.{entry:,.2f} x {qty:,.2f} units  ({entry_date})")
        print(f"  {'Invested':12} Rs.{invested_val:,.0f}")
        print(f"  {'Current':12} Rs.{current_val:,.0f}  (@ Rs.{current:,.2f}/unit)")
        print(f"  {'P&L':12} {pnl_str}  (Rs.{current_val - invested_val:+,.0f})")
        print(f"  {'Thesis':12} {thesis}")
        print(f"  {'Exit when':12} {exit_cond}")

    pnl_total = ctx["portfolio_pnl_pct"]
    n = len(holdings)
    total_gain = total_current - total_invested
    print(f"\n  {'-' * 50}")
    print(f"  Total invested:  Rs.{total_invested:,.0f}")
    print(f"  Total current:   Rs.{total_current:,.0f}  ({total_gain:+,.0f})")
    print(f"  Portfolio P&L:   {pnl_total:+.1f}%  |  {n} holding{'s' if n != 1 else ''}")
    print(f"{'=' * W}\n")


def cmd_add(args: list):
    """Interactively add or update a portfolio holding."""
    if not args:
        print("[ERROR] Provide a ticker: python run.py add RELIANCE.NS")
        return

    ticker = args[0].upper()
    if not ticker.endswith(".NS") and "=" not in ticker:
        ticker = ticker + ".NS"
        print(f"  Assuming NSE format: {ticker}")

    print(f"\nAdding {ticker} to portfolio...")

    # Try to fetch current price
    current_price = None
    try:
        from src.data.market_fetcher import YFINANCE_AVAILABLE
        if YFINANCE_AVAILABLE:
            import yfinance as yf
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                current_price = round(float(hist["Close"].iloc[-1]), 2)
                print(f"Current price (live from Yahoo Finance): Rs.{current_price:,.2f}")
    except Exception:
        pass

    if current_price is None:
        cp_str = input("Current price (Rs.): ").strip()
        try:
            current_price = float(cp_str.replace(",", ""))
        except ValueError:
            print("[ERROR] Invalid price. Aborting.")
            return

    # Collect remaining fields
    try:
        entry_str = input("Entry price (Rs.): ").strip().replace(",", "")
        entry_price = float(entry_str)
    except ValueError:
        print("[ERROR] Invalid entry price. Aborting.")
        return

    entry_date = input("Entry date (YYYY-MM-DD): ").strip()
    if not entry_date:
        entry_date = datetime.now().strftime("%Y-%m-%d")

    qty_str = input("Quantity (number of shares/units, press Enter to skip): ").strip()
    quantity = 1.0
    if qty_str:
        try:
            quantity = float(qty_str.replace(",", ""))
        except ValueError:
            print("  [WARN] Invalid quantity, defaulting to 1.")

    thesis = input("Thesis (one sentence - why did you buy?): ").strip()
    if not thesis:
        thesis = "No thesis provided."

    exit_condition = input("Exit condition (what would make you sell?): ").strip()
    if not exit_condition:
        exit_condition = "No exit condition set - review regularly."

    pnl_pct = ((current_price - entry_price) / entry_price) * 100
    invested_val = entry_price * quantity
    current_val = current_price * quantity

    memory = load_memory()
    memory.add_holding(
        ticker=ticker,
        entry_price=entry_price,
        entry_date=entry_date,
        current_price=current_price,
        unrealized_pnl_pct=pnl_pct,
        thesis=thesis,
        exit_condition=exit_condition,
        quantity=quantity,
    )

    print(f"\n[OK] Added {ticker} to portfolio.")
    print(f"     {quantity:,.2f} units | Entry Rs.{entry_price:,.2f} | Current Rs.{current_price:,.2f}")
    print(f"     Invested Rs.{invested_val:,.0f} | Current Rs.{current_val:,.0f} | P&L {pnl_pct:+.1f}%")
    print(f"     Thesis: {thesis}")
    print(f"     Exit when: {exit_condition}\n")


def cmd_remove(args: list):
    """Remove a holding from portfolio."""
    if not args:
        print("[ERROR] Provide a ticker: python run.py remove RELIANCE.NS")
        return

    ticker = args[0].upper()
    if not ticker.endswith(".NS") and "=" not in ticker:
        ticker = ticker + ".NS"

    memory = load_memory()
    holding = memory.get_holding_by_ticker(ticker)

    if not holding:
        print(f"[ERROR] {ticker} not found in portfolio.")
        print("  Current holdings:")
        ctx = memory.get_portfolio_context()
        for h in ctx["current_holdings"]:
            print(f"    - {h['ticker']}")
        return

    confirm = input(f"Remove {ticker} from portfolio? (y/N): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    memory.portfolio.holdings = [
        h for h in memory.portfolio.holdings if h.ticker != ticker
    ]
    memory.save_memory()
    print(f"[OK] Removed {ticker} from portfolio.")


def cmd_history(args: list):
    """Show decision history."""
    memory = load_memory()
    decisions = memory.portfolio.decisions

    print(f"\n{'=' * W}")
    print("  DECISION HISTORY")
    print(f"{'=' * W}")

    if not decisions:
        print("\n  No decisions recorded yet.")
        print("  Decisions are saved automatically after each portfolio analysis.")
        print(f"\n{'=' * W}\n")
        return

    for i, d in enumerate(reversed(decisions)):
        print(f"\n  [{len(decisions) - i}] {d.date}")
        print(f"  Recommendation: {d.system_recommendation}")
        print(f"  Action taken:   {d.action_taken}")
        if d.outcome_30d:
            correct = "[OK]" if d.was_recommendation_correct else "[!]"
            print(f"  30d outcome:    {correct} {d.outcome_30d}")
        if d.notes:
            print(f"  Notes:          {d.notes}")

    print(f"\n{'=' * W}\n")


def cmd_export(args: list):
    """Export last report to markdown."""
    if not LAST_REPORT_FILE.exists():
        print("[ERROR] No report to export. Run 'python run.py portfolio' first.")
        return

    try:
        with open(LAST_REPORT_FILE, encoding="utf-8") as f:
            result = json.load(f)
    except Exception as exc:
        print(f"[ERROR] Could not load last report: {exc}")
        return

    from src.core.reporter import save_report
    mode = result.get("mode", "portfolio")
    path = save_report(result, mode)
    print(f"[OK] Report exported to: {path}")


def cmd_run_analysis(mode: str, trigger: str, args: list):
    """Run a full analysis cycle (general, portfolio, rbi, or event)."""
    if not check_api_key():
        return

    no_live_data = "--no-live-data" in args
    save_flag = "--save" in args
    show_trail = "--show-trail" in args

    # Determine triggers
    trigger_map = {
        "rbi": ["rbi_fed_announcement"],
        "geopolitical": ["geopolitical_event"],
        "commodity": ["commodity_spike"],
    }
    triggers = trigger_map.get(trigger, ["scheduled_weekly_review"])

    # Load memory to get tickers
    memory = load_memory()
    ctx = memory.get_portfolio_context()
    holdings = ctx["current_holdings"]
    tickers = [h["ticker"] for h in holdings]

    # Warn if portfolio mode but no holdings
    if mode == "portfolio" and not tickers:
        print("\n[!] Portfolio is empty. Nothing to analyze.")
        print("    Add holdings first:  python run.py add RELIANCE.NS")
        print("    Or run general mode: python run.py general\n")
        return

    # Load live data
    data_summary = load_live_data(tickers if mode == "portfolio" else [], skip=no_live_data)

    # Print analysis summary
    if mode == "portfolio" and tickers and not no_live_data:
        print_analysis_header(tickers, data_summary)

    # Initialize workflow and run
    print(f"[RUN] Starting {mode.upper()} analysis...\n")
    try:
        workflow = HMASWorkflow(memory_file=MEMORY_FILE)
        result = workflow.run_full_cycle(triggers=triggers, mode=mode)
    except ValueError as exc:
        print(f"\n[ERROR] {exc}\n")
        return
    except Exception as exc:
        print(f"\n[ERROR] Analysis failed: {exc}\n")
        raise

    # Print the report
    workflow.print_full_report(result, show_signal_trail=show_trail)

    # Auto-record decision to memory (portfolio mode)
    if mode == "portfolio" and result.get("briefs"):
        try:
            _record_decisions(result)
        except Exception:
            pass

    # Save last report for export command
    save_last_report(result)

    # Save to file if --save flag
    if save_flag:
        try:
            path = save_report(result, mode)
            print(f"\n[OK] Report saved to: {path}")
        except Exception as exc:
            print(f"\n[WARN] Could not save report: {exc}")


def _record_decisions(result: dict):
    """Record analysis recommendations to portfolio memory."""
    memory = load_memory()
    briefs = result.get("briefs", [])
    if not briefs:
        return

    recs = []
    for b in briefs:
        ticker = b.get("ticker", "UNKNOWN")
        flag = b.get("flag", "HOLD")
        reason = b.get("reason", "")
        recs.append(f"{ticker}: {flag} - {reason}")

    rec_str = " | ".join(recs)
    memory.record_decision(
        system_recommendation=rec_str,
        action_taken="Pending - review and act",
        notes=f"Auto-recorded from {result.get('mode','portfolio')} analysis.",
    )


def cmd_watch(args: list):
    """Add a ticker to the buy watchlist."""
    if not args:
        print("[ERROR] Provide a ticker: python run.py watch RELIANCE.NS")
        return

    ticker = args[0].upper()
    if not ticker.endswith(".NS") and "=" not in ticker and "^" not in ticker:
        ticker = ticker + ".NS"
        print(f"  Assuming NSE format: {ticker}")

    # Try to fetch current price
    current_price = 0.0
    try:
        from src.data.market_fetcher import YFINANCE_AVAILABLE
        if YFINANCE_AVAILABLE:
            import yfinance as yf
            hist = yf.Ticker(ticker).history(period="5d")
            if not hist.empty:
                current_price = round(float(hist["Close"].iloc[-1]), 2)
                print(f"  Current price: Rs.{current_price:,.2f}")
    except Exception:
        pass

    reason = input("Why are you watching this? (thesis/setup): ").strip()
    if not reason:
        reason = "Under review."

    buy_condition = input("What specific condition must occur before buying?: ").strip()
    if not buy_condition:
        buy_condition = "To be defined."

    notes = input("Additional notes (optional, press Enter to skip): ").strip()

    memory = load_memory()
    item = memory.add_to_watchlist(
        ticker=ticker,
        reason=reason,
        target_buy_condition=buy_condition,
        current_price=current_price,
        notes=notes,
    )

    print(f"\n[OK] Added {ticker} to watchlist.")
    print(f"     Reason: {item.reason}")
    print(f"     Buy condition: {item.target_buy_condition}")
    print(f"     Run 'python run.py scan' to get a buy opportunity assessment.\n")


def cmd_unwatch(args: list):
    """Remove a ticker from the watchlist."""
    if not args:
        print("[ERROR] Provide a ticker: python run.py unwatch RELIANCE.NS")
        return

    ticker = args[0].upper()
    if not ticker.endswith(".NS") and "=" not in ticker and "^" not in ticker:
        ticker = ticker + ".NS"

    memory = load_memory()
    removed = memory.remove_from_watchlist(ticker)
    if removed:
        print(f"[OK] Removed {ticker} from watchlist.")
    else:
        print(f"[ERROR] {ticker} not found in watchlist.")
        watchlist = memory.get_watchlist()
        if watchlist:
            print("  Current watchlist:")
            for w in watchlist:
                print(f"    - {w.ticker}")
        else:
            print("  Watchlist is empty.")


def cmd_watchlist(args: list):
    """Show current watchlist."""
    memory = load_memory()
    watchlist = memory.get_watchlist()

    print(f"\n{'=' * W}")
    print("  WATCHLIST  (Buy Opportunity Monitor)")
    print(f"{'=' * W}")

    if not watchlist:
        print("\n  Watchlist is empty.")
        print("  Add tickers with:  python run.py watch TICKER.NS")
        print(f"\n{'=' * W}\n")
        return

    for w in watchlist:
        price_str = f"Rs.{w.current_price:,.2f}" if w.current_price else "price unknown"
        print()
        print(f"  {w.ticker}  ({price_str})  — added {w.added_date}")
        print(f"  {'Reason':14} {w.reason}")
        print(f"  {'Buy condition':14} {w.target_buy_condition}")
        if w.notes:
            print(f"  {'Notes':14} {w.notes}")

    print(f"\n  {len(watchlist)} ticker(s) on watchlist")
    print(f"  Run 'python run.py scan' to get buy opportunity assessment")
    print(f"{'=' * W}\n")


def cmd_scan(args: list):
    """Run watchlist buy opportunity scan."""
    if not check_api_key():
        return

    memory = load_memory()
    watchlist = memory.get_watchlist()

    if not watchlist:
        print("\n[!] Watchlist is empty. Nothing to scan.")
        print("    Add tickers with:  python run.py watch TICKER.NS")
        print("    Or use 'python run.py scout' to scan the full Nifty universe.\n")
        return

    no_live_data = "--no-live-data" in args
    save_flag = "--save" in args
    show_trail = "--show-trail" in args

    tickers = [w.ticker for w in watchlist]
    print(f"\n[SCAN] Scanning {len(tickers)} watchlist ticker(s): {', '.join(tickers)}")

    data_summary = load_live_data(tickers, skip=no_live_data)
    news = data_summary.get("news", {})
    print(f"\n  Loaded {news.get('india_items', 0)} India + {news.get('world_items', 0)} world news items")

    print(f"\n[RUN] Starting WATCHLIST SCAN analysis...\n")
    try:
        workflow = HMASWorkflow(memory_file=MEMORY_FILE)
        result = workflow.run_watchlist_scan(tickers=tickers)
    except ValueError as exc:
        print(f"\n[ERROR] {exc}\n")
        return
    except Exception as exc:
        print(f"\n[ERROR] Scan failed: {exc}\n")
        raise

    workflow.print_full_report(result, show_signal_trail=show_trail)
    save_last_report(result)

    if save_flag:
        try:
            path = save_report(result, "scan")
            print(f"\n[OK] Report saved to: {path}")
        except Exception as exc:
            print(f"\n[WARN] Could not save report: {exc}")


def cmd_scout(args: list):
    """
    Proactively scan for buy opportunities using HMAS v2 pipeline:
    macro intelligence → causal chain → web-search universe → verification
    → parallel stock research → top-5 selection.
    """
    if not check_api_key():
        return

    save_flag = "--save" in args
    show_trail = "--show-trail" in args

    print("\n[SCOUT v2] Macro-guided universe discovery + deep research")
    print("           Intelligence -> Macro chain -> Web search -> Verify -> Research -> Top 5")
    print("           Estimated time: 3-5 minutes\n")

    # Load previous run context for learning
    previous_context = _report_history.get_previous_context("scout")
    if previous_context:
        print("  [INFO] Previous scout context loaded — agents will learn from last run")

    try:
        from src.core.workflow_v2 import ScoutWorkflow
        workflow = ScoutWorkflow(memory_file=MEMORY_FILE)
        result = workflow.run(previous_context=previous_context)
    except ValueError as exc:
        print(f"\n[ERROR] {exc}\n")
        return
    except Exception as exc:
        print(f"\n[ERROR] Scout v2 failed: {exc}\n")
        raise

    workflow.print_report(result, show_trail=show_trail)
    save_last_report(result)

    try:
        path = save_report(result, "scout_v2")
        print(f"\n[OK] Report saved to: {path}")
    except Exception as exc:
        print(f"\n[WARN] Could not save report: {exc}")


def cmd_sync_holdings(args: list):
    """
    Parse broker xlsx files from the holdings/ folder and sync to portfolio memory.

    Stock ETF holdings (known ISIN) → added as portfolio holdings.
    Equity MF holdings              → added to watchlist as proxy ETFs.
    Debt MF holdings                → skipped (not NSE-tradeable).
    """
    folder = "holdings"
    # Allow custom folder: python run.py sync-holdings path/to/folder
    if args and not args[0].startswith("--"):
        folder = args[0]

    print(f"\n[SYNC] Reading holdings from '{folder}/' ...")

    try:
        from src.data.holdings_importer import sync_holdings_to_memory, print_import_report
    except ImportError as exc:
        print(f"[ERROR] Could not import holdings_importer: {exc}")
        print("        Make sure openpyxl is installed:  pip install openpyxl")
        return

    memory = load_memory()
    try:
        report = sync_holdings_to_memory(memory, folder=folder)
    except Exception as exc:
        print(f"[ERROR] Import failed: {exc}")
        raise

    print_import_report(report)


def cmd_run_portfolio_v2(args: list):
    """Run portfolio analysis using HMAS v2 pipeline."""
    if not check_api_key():
        return

    save_flag = "--save" in args
    show_trail = "--show-trail" in args

    memory = load_memory()
    ctx = memory.get_portfolio_context()
    if not ctx.get("current_holdings"):
        print("\n[!] Portfolio is empty. Nothing to analyse.")
        print("    Add holdings first:  python run.py add RELIANCE.NS\n")
        return

    print("\n[PORTFOLIO v2] Macro-guided portfolio review")
    print("               Intelligence -> Macro chain -> Per-holding research -> Advisor")
    print("               Estimated time: 3-5 minutes\n")

    # Load previous run context for learning
    previous_context = _report_history.get_previous_context("portfolio")
    if previous_context:
        print("  [INFO] Previous portfolio context loaded — agents will learn from last run")

    try:
        from src.core.workflow_v2 import PortfolioWorkflow
        workflow = PortfolioWorkflow(memory_file=MEMORY_FILE)
        result = workflow.run(previous_context=previous_context)
    except ValueError as exc:
        print(f"\n[ERROR] {exc}\n")
        return
    except Exception as exc:
        print(f"\n[ERROR] Portfolio v2 failed: {exc}\n")
        raise

    workflow.print_report(result, show_trail=show_trail)
    save_last_report(result)

    try:
        path = save_report(result, "portfolio_v2")
        print(f"\n[OK] Report saved to: {path}")
    except Exception as exc:
        print(f"\n[WARN] Could not save report: {exc}")


def cmd_portfolio_show_and_validate(args: list):
    """Validate portfolio file on load - check for missing fields."""
    memory = load_memory()
    ctx = memory.get_portfolio_context()
    holdings = ctx["current_holdings"]

    warnings_found = []
    for h in holdings:
        ticker = h["ticker"]
        if not h.get("exit_condition") or h["exit_condition"] == "No exit condition set - review regularly.":
            warnings_found.append(f"{ticker}: missing exit condition")
        if not h.get("thesis") or h["thesis"] == "No thesis provided.":
            warnings_found.append(f"{ticker}: missing thesis")

    if warnings_found:
        print("\n[!] Portfolio validation warnings:")
        for w in warnings_found:
            print(f"    - {w}")
        print("    Update with:  python run.py add TICKER.NS\n")


# -----------------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------------

def print_help():
    print(f"""
HMAS - Hierarchical Multi-Agent Investment System
{'=' * W}

Portfolio commands:
  python run.py portfolio          Full portfolio analysis (HOLD/WATCH/EXIT per holding)
  python run.py general            General India equity market read (no portfolio needed)
  python run.py show               Show portfolio holdings and P&L
  python run.py add TICKER.NS      Add or update a holding interactively
  python run.py remove TICKER.NS   Remove a holding
  python run.py history            Show decision history

Watchlist / Buy scanner commands:
  python run.py scout              Scan full Nifty universe for buy ideas this week (no watchlist needed)
  python run.py watch TICKER.NS    Add ticker to personal watchlist (with thesis + entry condition)
  python run.py unwatch TICKER.NS  Remove ticker from watchlist
  python run.py watchlist          Show watchlist (no API needed)
  python run.py scan               Scan your personal watchlist for buy opportunities

Quick analysis:
  python run.py rbi                RBI/Fed announcement quick analysis
  python run.py event geopolitical Geopolitical event quick analysis
  python run.py export             Export last report to markdown
  python run.py sync-holdings      Import holdings from holdings/*.xlsx into portfolio memory

Flags:
  --no-live-data                   Skip live yfinance fetch (use existing data)
  --save                           Save report to reports/ directory
  --show-trail                     Show full agent reasoning chains

Examples:
  python run.py scout                   # Best stock ideas for this week (full Nifty scan)
  python run.py general                 # Market overview + top opportunities
  python run.py add RELIANCE.NS         # Add a holding
  python run.py watch INFY.NS           # Add to personal watchlist
  python run.py scan --save             # Scan personal watchlist
  python run.py portfolio --show-trail  # Full portfolio review with reasoning chains
{'=' * W}
""")


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h", "help"):
        print_help()
        return

    command = args[0].lower()
    rest = args[1:]

    if command == "show":
        cmd_portfolio_show_and_validate(rest)
        cmd_show(rest)

    elif command == "add":
        cmd_add(rest)

    elif command == "remove":
        cmd_remove(rest)

    elif command == "history":
        cmd_history(rest)

    elif command == "export":
        cmd_export(rest)

    elif command == "portfolio":
        cmd_portfolio_show_and_validate(rest)
        cmd_run_portfolio_v2(rest)

    elif command == "general":
        cmd_run_analysis("general", "weekly", rest)

    elif command == "rbi":
        cmd_run_analysis("portfolio", "rbi", rest)

    elif command == "event":
        if not rest:
            print("[ERROR] Specify event type: python run.py event geopolitical")
            return
        event_type = rest[0].lower()
        valid_events = ["geopolitical", "commodity", "rbi"]
        if event_type not in valid_events:
            print(f"[ERROR] Unknown event type '{event_type}'. Valid: {', '.join(valid_events)}")
            return
        cmd_run_analysis("portfolio", event_type, rest[1:])

    elif command == "watch":
        cmd_watch(rest)

    elif command == "unwatch":
        cmd_unwatch(rest)

    elif command == "watchlist":
        cmd_watchlist(rest)

    elif command == "scan":
        cmd_scan(rest)

    elif command == "scout":
        cmd_scout(rest)

    elif command == "sync-holdings":
        cmd_sync_holdings(rest)

    else:
        print(f"[ERROR] Unknown command: '{command}'")
        print("Run 'python run.py --help' for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
