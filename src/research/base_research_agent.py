"""
BaseResearchAgent — shared data-fetching utilities for StockResearchAgent
and HoldingResearchAgent.

Provides:
  - fetch_live_data(ticker) → price, technicals, fundamentals from yfinance
  - fetch_stock_news(ticker, company_name) → recent headlines via Tavily
  - format_data_for_prompt(ticker, live_data, news, macro_summary, extra) → str
"""

from typing import Dict, Any, List, Optional

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

try:
    from src.data.news_fetcher import fetch_tavily_news
    _TAVILY_AVAILABLE = True
except ImportError:
    _TAVILY_AVAILABLE = False

from src.data.market_fetcher import calculate_rsi, calculate_macd, calculate_bollinger_bands


def fetch_live_data(ticker: str) -> Dict[str, Any]:
    """
    Fetch live price, technicals, and fundamentals for a single ticker.
    Returns a flat dict. Does NOT touch any global MCP singletons — safe for parallel use.
    """
    if not _YF_AVAILABLE:
        return {"ticker": ticker, "error": "yfinance not available", "current_price": 0}

    try:
        t = yf.Ticker(ticker)
        # Single fetch for 1y; slice last ~126 trading days (≈6 months) for technicals
        hist_1y = t.history(period="1y")

        if hist_1y.empty:
            return {"ticker": ticker, "error": "no price history", "current_price": 0}

        hist_6mo = hist_1y.iloc[-126:] if len(hist_1y) > 126 else hist_1y

        closes_6mo = hist_6mo["Close"].tolist()
        volumes_6mo = hist_6mo["Volume"].tolist()
        current_price = closes_6mo[-1]
        prev_close = closes_6mo[-2] if len(closes_6mo) >= 2 else current_price

        # 52W range — use full 1Y data
        closes_1y = hist_1y["Close"].tolist()
        high_52w = round(max(hist_1y["High"].tolist()), 2)
        low_52w = round(min(hist_1y["Low"].tolist()), 2)
        w52_position_pct = round(
            ((current_price - low_52w) / (high_52w - low_52w) * 100) if high_52w > low_52w else 50, 1
        )

        # Technicals
        rsi = round(calculate_rsi(closes_6mo), 1)
        macd_val, signal_val, macd_hist = calculate_macd(closes_6mo)
        bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(closes_6mo)

        # Moving averages
        ma50 = round(sum(closes_6mo[-50:]) / min(50, len(closes_6mo)), 2) if closes_6mo else 0
        ma200 = round(sum(closes_1y[-200:]) / min(200, len(closes_1y)), 2) if closes_1y else 0

        # Volume
        avg_vol_30d = int(sum(volumes_6mo[-30:]) / min(30, len(volumes_6mo))) if volumes_6mo else 0
        today_vol = int(volumes_6mo[-1]) if volumes_6mo else 0
        vol_vs_avg = round(today_vol / avg_vol_30d, 2) if avg_vol_30d > 0 else 1.0

        # Momentum
        mom_1m = round(((closes_6mo[-1] - closes_6mo[-21]) / closes_6mo[-21]) * 100, 1) if len(closes_6mo) >= 21 else 0
        mom_3m = round(((closes_6mo[-1] - closes_6mo[-63]) / closes_6mo[-63]) * 100, 1) if len(closes_6mo) >= 63 else 0

        # Fundamentals from yfinance info (best-effort)
        info = {}
        company_name = ticker.replace(".NS", "")
        sector = "Unknown"
        try:
            info = t.info or {}
            company_name = info.get("longName") or info.get("shortName") or company_name
            sector = info.get("sector") or info.get("industry") or "Unknown"
        except Exception:
            pass

        return {
            "ticker": ticker,
            "company_name": company_name,
            "sector": sector,
            "current_price": round(current_price, 2),
            "day_change_pct": round(((current_price - prev_close) / prev_close) * 100, 2) if prev_close else 0,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "w52_position_pct": w52_position_pct,
            "rsi": rsi,
            "macd": round(macd_val, 4),
            "macd_signal_line": round(signal_val, 4),
            "macd_histogram": round(macd_hist, 4),
            "macd_bias": "bullish" if macd_hist > 0 else "bearish",
            "above_ma50": current_price > ma50,
            "above_ma200": current_price > ma200,
            "ma50": ma50,
            "ma200": ma200,
            "bb_upper": round(bb_upper, 2),
            "bb_lower": round(bb_lower, 2),
            "bb_position": "above_mid" if current_price > bb_mid else "below_mid",
            "avg_vol_30d": avg_vol_30d,
            "vol_vs_avg": vol_vs_avg,
            "momentum_1m_pct": mom_1m,
            "momentum_3m_pct": mom_3m,
            # Fundamentals
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "roe_pct": round((info.get("returnOnEquity") or 0) * 100, 1) if info.get("returnOnEquity") else None,
            "debt_to_equity": info.get("debtToEquity"),
            "revenue_growth_pct": round((info.get("revenueGrowth") or 0) * 100, 1) if info.get("revenueGrowth") else None,
            "earnings_growth_pct": round((info.get("earningsGrowth") or 0) * 100, 1) if info.get("earningsGrowth") else None,
            "promoter_holding_pct": None,  # Not available via yfinance
            "market_cap": info.get("marketCap"),
            "dividend_yield_pct": round((info.get("dividendYield") or 0) * 100, 2) if info.get("dividendYield") else None,
        }
    except Exception as exc:
        return {"ticker": ticker, "error": str(exc), "current_price": 0, "company_name": ticker.replace(".NS", "")}


def fetch_stock_news(ticker: str, company_name: str, max_results: int = 6) -> List[str]:
    """
    Fetch recent news specific to a company via Tavily + yfinance news.
    Returns a list of headline strings.
    """
    headlines: List[str] = []

    # Tavily: company-specific news — single combined query
    if _TAVILY_AVAILABLE:
        short_name = company_name.split(" ")[0] if company_name else ticker.replace(".NS", "")
        query = f"{short_name} {ticker.replace('.NS','')} NSE India earnings results analyst 2025"
        for item in fetch_tavily_news(query, mcp_tag="india", max_results=max_results):
            h = f"[{item.get('source','')}] {item['title']}"
            if item.get("content") and item["content"] != item["title"]:
                h += f" — {item['content'][:150]}"
            if h not in headlines:
                headlines.append(h)

    # yfinance news fallback
    if _YF_AVAILABLE and len(headlines) < 3:
        try:
            t = yf.Ticker(ticker)
            raw_news = t.news or []
            for n in raw_news[:4]:
                content = n.get("content", {})
                title = content.get("title", n.get("title", ""))
                if title:
                    headlines.append(f"[Yahoo Finance] {title}")
        except Exception:
            pass

    return headlines[:max_results]


def format_data_block(
    ticker: str,
    live: Dict[str, Any],
    news: List[str],
    macro_summary: str,
    cached_context: str = "",
) -> str:
    """
    Format all data into a structured text block for LLM prompt injection.
    """
    cname = live.get("company_name", ticker)
    price = live.get("current_price", "N/A")
    day_chg = live.get("day_change_pct", 0)
    rsi = live.get("rsi", "N/A")
    macd_bias = live.get("macd_bias", "N/A")
    above_ma50 = "yes" if live.get("above_ma50") else "no"
    above_ma200 = "yes" if live.get("above_ma200") else "no"
    mom1m = live.get("momentum_1m_pct", "N/A")
    mom3m = live.get("momentum_3m_pct", "N/A")
    w52_pos = live.get("w52_position_pct", "N/A")
    high_52w = live.get("high_52w", "N/A")
    low_52w = live.get("low_52w", "N/A")
    pe = live.get("pe_ratio", "N/A")
    pb = live.get("pb_ratio", "N/A")
    roe = live.get("roe_pct", "N/A")
    de = live.get("debt_to_equity", "N/A")
    rev_g = live.get("revenue_growth_pct", "N/A")
    earn_g = live.get("earnings_growth_pct", "N/A")
    mktcap_cr = round(live.get("market_cap", 0) / 1e7, 0) if live.get("market_cap") else "N/A"

    news_block = "\n".join(f"  - {h}" for h in news) if news else "  No recent news available."

    parts = [
        f"## STOCK: {cname} ({ticker})",
        f"Sector: {live.get('sector','Unknown')}  |  Market cap: ₹{mktcap_cr}Cr",
        "",
        f"PRICE: ₹{price} ({day_chg:+.1f}% today)",
        f"52W: High ₹{high_52w}  Low ₹{low_52w}  Position: {w52_pos}th percentile",
        "",
        "TECHNICALS:",
        f"  RSI(14): {rsi}  |  MACD: {macd_bias}  |  Above MA50: {above_ma50}  |  Above MA200: {above_ma200}",
        f"  Momentum: 1M={mom1m}%  3M={mom3m}%",
        f"  MA50: ₹{live.get('ma50','N/A')}  MA200: ₹{live.get('ma200','N/A')}",
        "",
        "FUNDAMENTALS:",
        f"  PE: {pe}x  |  PB: {pb}x  |  ROE: {roe}%  |  D/E: {de}",
        f"  Revenue growth: {rev_g}%  |  Earnings growth: {earn_g}%",
        "",
        "RECENT NEWS:",
        news_block,
        "",
        "MACRO CONTEXT:",
        macro_summary,
    ]

    if cached_context:
        parts += ["", "PRIOR ANALYSIS (from cache):", cached_context]

    return "\n".join(parts)
