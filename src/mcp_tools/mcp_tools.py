"""MCP Tools - Data sources for all agents."""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum
from abc import ABC, abstractmethod


class NewsType(str, Enum):
    INDIA_BUSINESS = "india_business"
    WORLD_NEWS = "world_news"


@dataclass
class NewsItem:
    """A news item from any source."""
    title: str
    source: str
    timestamp: str
    content: str
    category: str  # e.g., "RBI Policy", "Earnings", "Geopolitical"
    relevance_to_india: Optional[str] = None  # How it impacts India


class IndiaNewsMCP:
    """India News MCP - Sources: Economic Times, Moneycontrol, BSE, RBI, SEBI."""

    def __init__(self):
        # In production, these would connect to real APIs
        self.news_items: List[NewsItem] = []

    def get_latest_news(self, limit: int = 10) -> List[NewsItem]:
        """Get latest India business news."""
        return self.news_items[:limit]

    def get_news_by_category(self, category: str) -> List[NewsItem]:
        """Get news filtered by category."""
        return [item for item in self.news_items if item.category == category]

    def add_news_item(self, news: NewsItem):
        """Add a news item (for testing/populate)."""
        self.news_items.insert(0, news)  # Add to front


class WorldNewsMCP:
    """World News MCP - Sources: Reuters, Bloomberg, BBC, FT."""

    def __init__(self):
        self.news_items: List[NewsItem] = []

    def get_latest_news(self, limit: int = 10) -> List[NewsItem]:
        """Get latest world news."""
        return self.news_items[:limit]

    def get_geopolitical_events(self) -> List[NewsItem]:
        """Get geopolitical events."""
        return [
            item
            for item in self.news_items
            if item.category in ["Geopolitical", "Trade", "Sanctions", "Elections"]
        ]

    def add_news_item(self, news: NewsItem):
        """Add a news item."""
        self.news_items.insert(0, news)


@dataclass
class PriceData:
    """Price and volume data for a security."""
    ticker: str
    price: float
    volume: int
    day_change_pct: float
    _52week_high: float
    _52week_low: float
    # NOTE: fii_dii_flow is a 5-day price momentum proxy (price_5d_chg × 10).
    # Real NSE FII/DII data is not available via free APIs.
    # Treat as a directional indicator only — not actual institutional flow in Cr.
    fii_dii_flow: Optional[float] = None
    # NOTE: delivery_pct is (today_volume / 20d_avg_volume × 50) — a relative volume proxy.
    # Real NSE delivery % requires paid data. Use only for relative conviction signal.
    delivery_pct: Optional[float] = None
    delivery_pct: Optional[float] = None


class MarketMCP:
    """Market MCP - NSE/BSE live prices, volume, FII/DII, delivery."""

    def __init__(self):
        self.price_data: Dict[str, PriceData] = {}

    def get_price(self, ticker: str) -> Optional[PriceData]:
        """Get current price data for a security."""
        return self.price_data.get(ticker)

    def get_multiple_prices(self, tickers: List[str]) -> Dict[str, PriceData]:
        """Get price data for multiple securities."""
        return {ticker: self.price_data[ticker] for ticker in tickers if ticker in self.price_data}

    def get_fii_flow(self, ticker: str) -> Optional[float]:
        """Get FII/DII flow for a security."""
        data = self.price_data.get(ticker)
        return data.fii_dii_flow if data else None

    def set_price(self, ticker: str, data: PriceData):
        """Set price data for a security."""
        self.price_data[ticker] = data


@dataclass
class TechnicalData:
    """Technical indicators for a security."""
    ticker: str
    rsi: float
    macd: float  # MACD line value
    macd_signal: float
    macd_histogram: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    current_price: float
    _52week_high: float
    _52week_low: float


class QuantMCP:
    """Quant MCP - Technical indicators: RSI, MACD, Bollinger Bands."""

    def __init__(self):
        self.technical_data: Dict[str, TechnicalData] = {}

    def get_technicals(self, ticker: str) -> Optional[TechnicalData]:
        """Get technical indicators for a security."""
        return self.technical_data.get(ticker)

    def get_technicals_multiple(self, tickers: List[str]) -> Dict[str, TechnicalData]:
        """Get technicals for multiple securities."""
        return {
            ticker: self.technical_data[ticker]
            for ticker in tickers
            if ticker in self.technical_data
        }

    def set_technicals(self, ticker: str, data: TechnicalData):
        """Set technical data for a security."""
        self.technical_data[ticker] = data

    def is_oversold(self, ticker: str) -> bool:
        """Check if RSI < 30 (oversold)."""
        data = self.technical_data.get(ticker)
        return data.rsi < 30 if data else False

    def is_overbought(self, ticker: str) -> bool:
        """Check if RSI > 70 (overbought)."""
        data = self.technical_data.get(ticker)
        return data.rsi > 70 if data else False


@dataclass
class MacroData:
    """Macro data for analysis."""
    indicator: str
    value: float
    timestamp: str
    source: str  # e.g., "RBI", "Fed", "OPEC"


class MacroMCP:
    """Macro MCP - RBI minutes, Fed decisions, Brent crude, Gold, metrics."""

    def __init__(self):
        self.macro_data: List[MacroData] = []

    def get_rbi_data(self) -> List[MacroData]:
        """Get RBI-related macro data."""
        return [item for item in self.macro_data if "RBI" in item.source]

    def get_fed_data(self) -> List[MacroData]:
        """Get Fed-related macro data."""
        return [item for item in self.macro_data if "Fed" in item.source]

    def get_commodity_prices(self) -> Dict[str, float]:
        """Get commodity prices: oil, gold, metals."""
        commodities = {}
        for item in self.macro_data:
            if item.indicator in ["Brent Crude", "Gold", "Metals Index"]:
                commodities[item.indicator] = item.value
        return commodities

    def get_indicator(self, indicator: str) -> Optional[float]:
        """Get value for a specific indicator."""
        for item in self.macro_data:
            if item.indicator == indicator:
                return item.value
        return None

    def add_data(self, data: MacroData):
        """Add macro data point."""
        self.macro_data.insert(0, data)


@dataclass
class FundamentalData:
    """Fundamental analysis data for a security, sourced from yfinance t.info."""
    ticker: str
    # Valuation
    pe_ratio: Optional[float] = None          # Trailing P/E
    forward_pe: Optional[float] = None        # Forward P/E
    pb_ratio: Optional[float] = None          # Price-to-Book
    ps_ratio: Optional[float] = None          # Price-to-Sales
    ev_ebitda: Optional[float] = None         # EV/EBITDA
    # Quality
    roe: Optional[float] = None               # Return on Equity (%)
    roa: Optional[float] = None               # Return on Assets (%)
    debt_to_equity: Optional[float] = None    # D/E ratio
    current_ratio: Optional[float] = None     # Current ratio
    gross_margin: Optional[float] = None      # Gross margin (%)
    operating_margin: Optional[float] = None  # Operating margin (%)
    net_margin: Optional[float] = None        # Net margin (%)
    # Growth
    revenue_growth: Optional[float] = None    # YoY revenue growth (%)
    earnings_growth: Optional[float] = None   # YoY earnings growth (%)
    eps_ttm: Optional[float] = None           # Trailing EPS
    # Analyst targets
    analyst_target_price: Optional[float] = None
    analyst_recommendation: Optional[str] = None  # "buy", "hold", "sell"
    # Context
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None        # In Cr (converted from USD if needed)


class FundamentalMCP:
    """Fundamental MCP — valuation, quality, and growth data per ticker."""

    def __init__(self):
        self.data: Dict[str, FundamentalData] = {}

    def set_fundamentals(self, ticker: str, data: FundamentalData):
        self.data[ticker] = data

    def get_fundamentals(self, ticker: str) -> Optional[FundamentalData]:
        return self.data.get(ticker)

    def get_all(self) -> Dict[str, FundamentalData]:
        return dict(self.data)


# Singleton instances for the system
india_news_mcp = IndiaNewsMCP()
world_news_mcp = WorldNewsMCP()
market_mcp = MarketMCP()
quant_mcp = QuantMCP()
macro_mcp = MacroMCP()
fundamental_mcp = FundamentalMCP()
