"""
market_fetcher.py — Fetches live market data from Yahoo Finance for NSE tickers.

Usage:
    from src.data.market_fetcher import populate_mcps
    tickers = ["RELIANCE.NS", "INFY.NS"]
    populate_mcps(tickers)  # Fills market_mcp, quant_mcp, macro_mcp with live data

NSE ticker format: append .NS to NSE symbols (e.g., RELIANCE.NS, INFY.NS, TCS.NS)
Commodity tickers: GC=F (gold), BZ=F (Brent crude), CL=F (WTI crude)
"""

import warnings
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

from src.mcp_tools.mcp_tools import (
    market_mcp, quant_mcp, macro_mcp, india_news_mcp, fundamental_mcp,
    PriceData, TechnicalData, MacroData, NewsItem, FundamentalData,
)


# ─────────────────────────────────────────────────────────────────────────────
# Technical indicator calculations (no extra dependencies)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate RSI (Relative Strength Index) for a price series."""
    if len(prices) < period + 1:
        return 50.0  # Neutral default if insufficient data
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return [prices[-1]] if prices else [0.0]
    k = 2.0 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema


def calculate_macd(
    prices: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple:
    """
    Calculate MACD line, signal line, and histogram.
    Returns (macd_value, signal_value, histogram_value).
    """
    if len(prices) < slow + signal:
        return 0.0, 0.0, 0.0
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)

    # Align: ema_slow starts later — align both to same length
    offset = len(ema_fast) - len(ema_slow)
    ema_fast_aligned = ema_fast[offset:] if offset > 0 else ema_fast

    macd_line = [f - s for f, s in zip(ema_fast_aligned, ema_slow)]
    if len(macd_line) < signal:
        return macd_line[-1], macd_line[-1], 0.0
    signal_line = calculate_ema(macd_line, signal)
    macd_val = macd_line[-1]
    signal_val = signal_line[-1]
    histogram = macd_val - signal_val
    return round(macd_val, 4), round(signal_val, 4), round(histogram, 4)


def calculate_bollinger_bands(
    prices: List[float], period: int = 20, num_std: float = 2.0
) -> tuple:
    """
    Calculate Bollinger Bands (upper, middle, lower).
    Returns (upper, middle, lower).
    """
    if len(prices) < period:
        p = prices[-1] if prices else 0.0
        return p * 1.02, p, p * 0.98
    window = prices[-period:]
    middle = sum(window) / period
    variance = sum((p - middle) ** 2 for p in window) / period
    std = variance ** 0.5
    upper = middle + num_std * std
    lower = middle - num_std * std
    return round(upper, 2), round(middle, 2), round(lower, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Main data fetch
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ticker_data(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetch all data for one NSE ticker via yfinance.

    Returns dict with price, technicals, and news — or None on failure.
    """
    if not YFINANCE_AVAILABLE:
        print(f"  [WARN] yfinance not installed — skipping live data for {ticker}")
        return None
    try:
        t = yf.Ticker(ticker)

        # 3 months of history for technicals
        hist_3mo = t.history(period="3mo")
        # 1 year for 52-week high/low
        hist_1y = t.history(period="1y")

        if hist_3mo.empty or hist_1y.empty:
            print(f"  [WARN] No price history for {ticker} — skipping")
            return None

        closes_3mo = hist_3mo["Close"].tolist()
        closes_1y = hist_1y["Close"].tolist()

        current_price = closes_3mo[-1]
        prev_close = closes_3mo[-2] if len(closes_3mo) >= 2 else current_price
        day_change_pct = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0.0

        high_52w = max(hist_1y["High"].tolist())
        low_52w = min(hist_1y["Low"].tolist())

        # Volume — use most recent day
        volume = int(hist_3mo["Volume"].iloc[-1]) if not hist_3mo["Volume"].empty else 0

        # DELIVERY % — estimated proxy only.
        # Real NSE delivery data requires the NSE Bhavcopy or a paid data vendor.
        # This uses: (today_volume / 20d_avg_volume) × 50, capped at 100.
        # A value >50 means above-average volume participation (higher conviction signal).
        avg_vol_20 = hist_3mo["Volume"].tail(20).mean()
        delivery_pct_proxy = min(100.0, (volume / avg_vol_20 * 50)) if avg_vol_20 > 0 else 50.0

        # FII/DII FLOW — estimated proxy only.
        # Real NSE FII/DII data is published daily at nseindia.com but requires scraping or paid API.
        # This uses: 5-day price change × 10, expressed as a Cr-scale directional estimate.
        # Positive = price has been rising (accumulation bias), Negative = falling (distribution bias).
        price_5d_chg = 0.0
        if len(closes_3mo) >= 5:
            price_5d_chg = ((closes_3mo[-1] - closes_3mo[-5]) / closes_3mo[-5]) * 100
        fii_proxy = round(price_5d_chg * 10, 1)

        # Technical indicators
        rsi = calculate_rsi(closes_3mo)
        macd_val, signal_val, histogram = calculate_macd(closes_3mo)
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(closes_3mo)

        # News from yfinance
        news_items = []
        try:
            raw_news = t.news or []
            for n in raw_news[:5]:
                content = n.get("content", {})
                title = content.get("title", n.get("title", "No title"))
                source_info = content.get("provider", {})
                source = source_info.get("displayName", "Yahoo Finance") if isinstance(source_info, dict) else "Yahoo Finance"
                news_items.append({
                    "title": title,
                    "source": source,
                    "ticker": ticker,
                })
        except Exception:
            pass

        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "day_change_pct": round(day_change_pct, 2),
            "volume": volume,
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "delivery_pct": round(delivery_pct_proxy, 1),
            "fii_proxy": fii_proxy,
            "rsi": round(rsi, 2),
            "macd": macd_val,
            "macd_signal": signal_val,
            "macd_histogram": histogram,
            "bb_upper": bb_upper,
            "bb_middle": bb_middle,
            "bb_lower": bb_lower,
            "news": news_items,
        }

    except Exception as exc:
        print(f"  [WARN] Failed to fetch data for {ticker}: {exc}")
        return None


def fetch_commodity_data() -> Dict[str, float]:
    """
    Fetch live commodity prices: Gold (GC=F), Brent crude (BZ=F).
    Returns dict of indicator -> value.
    """
    if not YFINANCE_AVAILABLE:
        return {}

    commodities = {}
    commodity_map = {
        "GC=F": "Gold",
        "BZ=F": "Brent Crude",
        "CL=F": "WTI Crude",
        "^GSPC": "S&P 500",
        "^IXIC": "NASDAQ",
        "DX-Y.NYB": "USD Index",
        "^TNX": "US 10Y Yield",
    }

    for symbol, name in commodity_map.items():
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="5d")
            if not hist.empty:
                price = hist["Close"].iloc[-1]
                commodities[name] = round(float(price), 2)
        except Exception as exc:
            print(f"  [WARN] Could not fetch {name} ({symbol}): {exc}")

    return commodities


def fetch_fundamentals(ticker: str) -> Optional[FundamentalData]:
    """
    Fetch fundamental data for a ticker via yfinance t.info.

    Returns FundamentalData or None on failure.
    Note: yfinance info data comes from Yahoo Finance — verify key ratios independently
    for investment decisions. Market cap is reported in USD by Yahoo; we store as-is.
    """
    if not YFINANCE_AVAILABLE:
        return None
    try:
        info = yf.Ticker(ticker).info
        if not info or info.get("regularMarketPrice") is None:
            return None

        def _pct(val) -> Optional[float]:
            """Convert decimal ratio to percentage."""
            return round(val * 100, 2) if val is not None else None

        return FundamentalData(
            ticker=ticker,
            pe_ratio=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            pb_ratio=info.get("priceToBook"),
            ps_ratio=info.get("priceToSalesTrailing12Months"),
            ev_ebitda=info.get("enterpriseToEbitda"),
            roe=_pct(info.get("returnOnEquity")),
            roa=_pct(info.get("returnOnAssets")),
            debt_to_equity=info.get("debtToEquity"),
            current_ratio=info.get("currentRatio"),
            gross_margin=_pct(info.get("grossMargins")),
            operating_margin=_pct(info.get("operatingMargins")),
            net_margin=_pct(info.get("profitMargins")),
            revenue_growth=_pct(info.get("revenueGrowth")),
            earnings_growth=_pct(info.get("earningsGrowth")),
            eps_ttm=info.get("trailingEps"),
            analyst_target_price=info.get("targetMeanPrice"),
            analyst_recommendation=info.get("recommendationKey"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            market_cap=info.get("marketCap"),
        )
    except Exception as exc:
        print(f"  [WARN] Failed to fetch fundamentals for {ticker}: {exc}")
        return None


def fetch_nse_fii_dii() -> Optional[Dict[str, Any]]:
    """
    Fetch market-level FII/DII daily data from NSE India.

    Endpoint: https://www.nseindia.com/api/fiidiiTradeReact
    Returns the latest entry (today's or most recent trading day's data).

    NOTE: NSE requires a browser session cookie. This function attempts to
    establish one via a homepage visit first. May fail if NSE changes their
    anti-bot measures — treat as best-effort.

    Returns dict with keys: date, fii_buy_value, fii_sell_value, fii_net,
    dii_buy_value, dii_sell_value, dii_net (all values in ₹ Cr).
    Returns None if fetch fails.
    """
    if not REQUESTS_AVAILABLE:
        return None

    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    }
    try:
        # Step 1: Hit the homepage to acquire session cookies
        session.get("https://www.nseindia.com/", headers=headers, timeout=8)
        # Step 2: Fetch FII/DII data
        resp = session.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            headers=headers,
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        # API returns list of records; most recent is first
        latest = data[0] if isinstance(data, list) else data
        return {
            "date": latest.get("date", ""),
            "fii_buy_value": float(latest.get("fiiBuyValue", 0) or 0),
            "fii_sell_value": float(latest.get("fiiSellValue", 0) or 0),
            "fii_net": float(latest.get("fiiNetValue", 0) or 0),
            "dii_buy_value": float(latest.get("diiBuyValue", 0) or 0),
            "dii_sell_value": float(latest.get("diiSellValue", 0) or 0),
            "dii_net": float(latest.get("diiNetValue", 0) or 0),
        }
    except Exception as exc:
        print(f"  [WARN] NSE FII/DII fetch failed: {type(exc).__name__} — using proxy")
        return None


def populate_mcps(tickers: List[str]) -> Dict[str, Any]:
    """
    Fetch live data for all tickers and populate market_mcp, quant_mcp, and macro_mcp.

    Args:
        tickers: List of NSE tickers in yfinance format (e.g., ["RELIANCE.NS", "INFY.NS"])

    Returns:
        Summary dict with counts and any warnings.
    """
    if not YFINANCE_AVAILABLE:
        print("  [WARN] yfinance not installed. Run: pip install yfinance>=0.2.40")
        return {"success": False, "reason": "yfinance not installed"}

    summary = {
        "tickers_fetched": [],
        "tickers_failed": [],
        "news_items_added": 0,
        "commodities_fetched": [],
        "fii_dii_real": None,
    }

    # Attempt real NSE FII/DII data first
    print("    Fetching NSE FII/DII data...", end=" ", flush=True)
    fii_dii_real = fetch_nse_fii_dii()
    if fii_dii_real:
        fii_net = fii_dii_real["fii_net"]
        dii_net = fii_dii_real["dii_net"]
        print(f"FII net Rs.{fii_net:+,.0f}Cr  DII net Rs.{dii_net:+,.0f}Cr")
        macro_mcp.add_data(MacroData(
            indicator="FII Net Flow",
            value=fii_net,
            timestamp=datetime.now().isoformat(),
            source="NSE India",
        ))
        macro_mcp.add_data(MacroData(
            indicator="DII Net Flow",
            value=dii_net,
            timestamp=datetime.now().isoformat(),
            source="NSE India",
        ))
        summary["fii_dii_real"] = fii_dii_real
    else:
        print("unavailable — will use price proxy per ticker")

    print(f"  [DATA] Fetching live data for {len(tickers)} ticker(s) from Yahoo Finance...")

    for ticker in tickers:
        print(f"    Fetching {ticker}...", end=" ", flush=True)
        data = fetch_ticker_data(ticker)

        if data is None:
            summary["tickers_failed"].append(ticker)
            print("FAILED")
            continue

        # Populate market_mcp
        market_mcp.set_price(ticker, PriceData(
            ticker=ticker,
            price=data["current_price"],
            volume=data["volume"],
            day_change_pct=data["day_change_pct"],
            _52week_high=data["high_52w"],
            _52week_low=data["low_52w"],
            fii_dii_flow=data["fii_proxy"],
            delivery_pct=data["delivery_pct"],
        ))

        # Populate quant_mcp
        quant_mcp.set_technicals(ticker, TechnicalData(
            ticker=ticker,
            rsi=data["rsi"],
            macd=data["macd"],
            macd_signal=data["macd_signal"],
            macd_histogram=data["macd_histogram"],
            bb_upper=data["bb_upper"],
            bb_middle=data["bb_middle"],
            bb_lower=data["bb_lower"],
            current_price=data["current_price"],
            _52week_high=data["high_52w"],
            _52week_low=data["low_52w"],
        ))

        # Populate fundamental_mcp
        fund_data = fetch_fundamentals(ticker)
        if fund_data:
            fundamental_mcp.set_fundamentals(ticker, fund_data)

        # Add ticker-specific news to india_news_mcp
        for news in data["news"]:
            india_news_mcp.add_news_item(NewsItem(
                title=news["title"],
                source=news["source"],
                timestamp=datetime.now().isoformat(),
                content=news["title"],
                category="Stock News",
                relevance_to_india=f"Relevant to {news['ticker']}",
            ))
            summary["news_items_added"] += 1

        summary["tickers_fetched"].append(ticker)
        p = data["current_price"]
        chg = data["day_change_pct"]
        print(f"Rs.{p:.0f} ({chg:+.1f}%)")

        # Update portfolio memory with live price if holding exists
        _update_memory_price(ticker, data["current_price"])

    # Fetch commodities and macro data
    print("    Fetching commodity/macro data...", end=" ", flush=True)
    commodities = fetch_commodity_data()
    for name, price in commodities.items():
        macro_mcp.add_data(MacroData(
            indicator=name,
            value=price,
            timestamp=datetime.now().isoformat(),
            source="Yahoo Finance",
        ))
        summary["commodities_fetched"].append(name)
    if commodities:
        print(f"Gold={commodities.get('Gold', 'N/A')}, Brent={commodities.get('Brent Crude', 'N/A')}")
    else:
        print("no data")

    return summary


def _update_memory_price(ticker: str, current_price: float):
    """Update portfolio memory with live price for holdings and watchlist items."""
    try:
        from pathlib import Path
        from src.memory.memory_mcp import MemoryMCP
        memory = MemoryMCP(Path("portfolio_memory.json"))
        if memory.get_holding_by_ticker(ticker):
            memory.update_holding_price(ticker, current_price)
        if memory.get_watch_item(ticker):
            memory.update_watch_price(ticker, current_price)
    except Exception:
        pass  # Non-critical — memory update failure does not block analysis
