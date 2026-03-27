"""Memory MCP - The brain of the investment system."""

import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class ThesisStatus(str, Enum):
    INTACT = "intact"
    WEAKENING = "weakening"
    BROKEN = "broken"


class Flag(str, Enum):
    HOLD = "hold"
    WATCH = "watch"
    EXIT_CONDITION_APPROACHING = "exit_condition_approaching"


@dataclass
class Holding:
    """A single holding in the portfolio."""
    ticker: str
    entry_price: float
    entry_date: str  # YYYY-MM-DD format
    current_price: float
    unrealized_pnl_pct: float
    thesis: str  # One-sentence thesis
    exit_condition: str  # Explicit exit condition
    quantity: float = 1.0  # units/shares held — used for weighted portfolio P&L


@dataclass
class Decision:
    """A recorded decision from the system."""
    date: str  # YYYY-MM-DD format
    system_recommendation: str
    action_taken: str
    outcome_30d: Optional[str] = None
    was_recommendation_correct: Optional[bool] = None
    notes: str = ""


@dataclass
class InvalidatedThesis:
    """A position where the original thesis no longer holds."""
    ticker: str
    original_thesis: str
    invalidation_reason: str
    date_invalidated: str  # YYYY-MM-DD format
    action_taken: str


@dataclass
class WatchItem:
    """A ticker being monitored for a future buy opportunity."""
    ticker: str
    reason: str              # Why this ticker is being watched (thesis/setup)
    target_buy_condition: str  # Specific condition that must trigger before buying
    added_date: str          # YYYY-MM-DD format
    current_price: float = 0.0
    notes: str = ""          # Optional additional context


@dataclass
class PortfolioMemory:
    """The complete memory structure for the portfolio."""
    holdings: List[Holding] = field(default_factory=list)
    decisions: List[Decision] = field(default_factory=list)
    invalidated_theses: List[InvalidatedThesis] = field(default_factory=list)
    watchlist: List[WatchItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "holdings": [asdict(h) for h in self.holdings],
            "decisions": [asdict(d) for d in self.decisions],
            "invalidated_theses": [asdict(it) for it in self.invalidated_theses],
            "watchlist": [asdict(w) for w in self.watchlist],
        }


class MemoryMCP:
    """Memory MCP - Interface to portfolio memory."""

    def __init__(self, memory_file: Optional[Path] = None):
        self.memory_file = memory_file or Path("portfolio_memory.json")
        self.portfolio = self._load_memory()

    def _load_memory(self) -> PortfolioMemory:
        """Load memory from file or create new."""
        if self.memory_file.exists():
            with open(self.memory_file, "r") as f:
                data = json.load(f)
                portfolio = PortfolioMemory()
                portfolio.holdings = [
                    Holding(**{**h, "quantity": h.get("quantity", 1.0)})
                    for h in data.get("holdings", [])
                ]
                portfolio.decisions = [Decision(**d) for d in data.get("decisions", [])]
                portfolio.invalidated_theses = [
                    InvalidatedThesis(**it)
                    for it in data.get("invalidated_theses", [])
                ]
                portfolio.watchlist = [
                    WatchItem(**w) for w in data.get("watchlist", [])
                ]
                return portfolio
        return PortfolioMemory()

    def save_memory(self):
        """Save memory to file."""
        with open(self.memory_file, "w") as f:
            json.dump(self.portfolio.to_dict(), f, indent=2)

    def add_holding(
        self,
        ticker: str,
        entry_price: float,
        entry_date: str,
        current_price: float,
        unrealized_pnl_pct: float,
        thesis: str,
        exit_condition: str,
        quantity: float = 1.0,
    ) -> Holding:
        """Add a new holding to the portfolio, or update if ticker already exists."""
        existing = self.get_holding_by_ticker(ticker)
        if existing:
            existing.current_price = current_price
            existing.unrealized_pnl_pct = unrealized_pnl_pct
            existing.thesis = thesis
            existing.exit_condition = exit_condition
            existing.quantity = quantity
            self.save_memory()
            return existing
        holding = Holding(
            ticker=ticker,
            entry_price=entry_price,
            entry_date=entry_date,
            current_price=current_price,
            unrealized_pnl_pct=unrealized_pnl_pct,
            thesis=thesis,
            exit_condition=exit_condition,
            quantity=quantity,
        )
        self.portfolio.holdings.append(holding)
        self.save_memory()
        return holding

    def update_holding_price(self, ticker: str, current_price: float):
        """Update current price and P&L for a holding."""
        for holding in self.portfolio.holdings:
            if holding.ticker == ticker:
                holding.current_price = current_price
                holding.unrealized_pnl_pct = (
                    (current_price - holding.entry_price) / holding.entry_price
                ) * 100
                self.save_memory()
                return holding
        raise ValueError(f"Holding {ticker} not found")

    def record_decision(
        self,
        system_recommendation: str,
        action_taken: str,
        notes: str = "",
    ) -> Decision:
        """Record a decision made by the system."""
        decision = Decision(
            date=datetime.now().strftime("%Y-%m-%d"),
            system_recommendation=system_recommendation,
            action_taken=action_taken,
            notes=notes,
        )
        self.portfolio.decisions.append(decision)
        self.save_memory()
        return decision

    def update_decision_outcome(
        self, index: int, outcome_30d: str, was_correct: bool, notes: str = ""
    ):
        """Update decision with 30-day outcome."""
        if 0 <= index < len(self.portfolio.decisions):
            self.portfolio.decisions[index].outcome_30d = outcome_30d
            self.portfolio.decisions[index].was_recommendation_correct = was_correct
            if notes:
                self.portfolio.decisions[index].notes = notes
            self.save_memory()

    def mark_thesis_invalid(
        self,
        ticker: str,
        original_thesis: str,
        invalidation_reason: str,
        action_taken: str = "Still holding — review immediately",
    ) -> InvalidatedThesis:
        """Mark a thesis as invalidated."""
        invalid = InvalidatedThesis(
            ticker=ticker,
            original_thesis=original_thesis,
            invalidation_reason=invalidation_reason,
            date_invalidated=datetime.now().strftime("%Y-%m-%d"),
            action_taken=action_taken,
        )
        self.portfolio.invalidated_theses.append(invalid)
        self.save_memory()
        return invalid

    # ── Watchlist CRUD ──────────────────────────────────────────────────────

    def add_to_watchlist(
        self,
        ticker: str,
        reason: str,
        target_buy_condition: str,
        current_price: float = 0.0,
        notes: str = "",
    ) -> WatchItem:
        """Add a ticker to the watchlist. Updates if already present."""
        existing = self.get_watch_item(ticker)
        if existing:
            existing.reason = reason
            existing.target_buy_condition = target_buy_condition
            existing.current_price = current_price
            if notes:
                existing.notes = notes
            self.save_memory()
            return existing
        item = WatchItem(
            ticker=ticker,
            reason=reason,
            target_buy_condition=target_buy_condition,
            added_date=datetime.now().strftime("%Y-%m-%d"),
            current_price=current_price,
            notes=notes,
        )
        self.portfolio.watchlist.append(item)
        self.save_memory()
        return item

    def remove_from_watchlist(self, ticker: str) -> bool:
        """Remove a ticker from the watchlist. Returns True if found and removed."""
        before = len(self.portfolio.watchlist)
        self.portfolio.watchlist = [
            w for w in self.portfolio.watchlist if w.ticker != ticker
        ]
        if len(self.portfolio.watchlist) < before:
            self.save_memory()
            return True
        return False

    def get_watch_item(self, ticker: str) -> Optional[WatchItem]:
        """Get a watchlist item by ticker."""
        for w in self.portfolio.watchlist:
            if w.ticker == ticker:
                return w
        return None

    def get_watchlist(self) -> List[WatchItem]:
        """Return the full watchlist."""
        return list(self.portfolio.watchlist)

    def update_watch_price(self, ticker: str, current_price: float):
        """Update current price for a watchlist item (called during data fetch)."""
        item = self.get_watch_item(ticker)
        if item:
            item.current_price = current_price
            self.save_memory()

    def get_holding_by_ticker(self, ticker: str) -> Optional[Holding]:
        """Get a holding by ticker."""
        for holding in self.portfolio.holdings:
            if holding.ticker == ticker:
                return holding
        return None

    def get_portfolio_context(self) -> Dict[str, Any]:
        """Get full portfolio context as a string for agents."""
        context = {
            "current_holdings": [asdict(h) for h in self.portfolio.holdings],
            "recent_decisions": [
                asdict(d) for d in self.portfolio.decisions[-5:]
            ],  # Last 5
            "invalidated_theses": [asdict(it) for it in self.portfolio.invalidated_theses],
            "total_holdings": len(self.portfolio.holdings),
            "portfolio_pnl_pct": self._calculate_total_pnl(),
        }
        return context

    def _calculate_total_pnl(self) -> float:
        """Calculate total portfolio P&L percentage, weighted by actual invested amount."""
        if not self.portfolio.holdings:
            return 0.0
        total_invested = sum(h.entry_price * h.quantity for h in self.portfolio.holdings)
        total_current = sum(h.current_price * h.quantity for h in self.portfolio.holdings)
        if total_invested == 0:
            return 0.0
        return ((total_current - total_invested) / total_invested) * 100


def get_portfolio_context_string(memory: MemoryMCP) -> str:
    """Format portfolio context as a readable string for agent prompts."""
    context = memory.get_portfolio_context()
    holdings_str = "\n".join(
        [
            f"  - {h['ticker']}: Entry ₹{h['entry_price']}, Current ₹{h['current_price']}, "
            f"P&L {h['unrealized_pnl_pct']:+.1f}% | Thesis: {h['thesis']}"
            for h in context["current_holdings"]
        ]
    )
    invalid_str = "\n".join(
        [
            f"  - {it['ticker']}: {it['invalidation_reason']}"
            for it in context["invalidated_theses"]
        ]
    )
    watchlist = memory.get_watchlist()
    watchlist_str = "\n".join(
        [
            f"  - {w.ticker}: {w.reason} | Buy condition: {w.target_buy_condition}"
            for w in watchlist
        ]
    ) if watchlist else "  - None"
    return f"""
=== PORTFOLIO CONTEXT ===
Current Holdings ({context['total_holdings']} positions):
{holdings_str}
Portfolio P&L: {context['portfolio_pnl_pct']:+.1f}%

Recent Decisions (last 5):
{chr(10).join([f"  - {d['date']}: {d['system_recommendation']}" for d in context['recent_decisions']])}

Invalidated Theses:
{invalid_str if invalid_str else "  - None"}

Watchlist ({len(watchlist)} tickers being monitored):
{watchlist_str}
"""
