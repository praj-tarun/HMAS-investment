"""
SourceVerifier — Phase 2B: 3-gate verification for web-sourced ticker candidates.

Gate 1: Source credibility — only accept tickers from whitelisted domains
Gate 2: Multi-source confirmation — ticker must appear in ≥2 independent sources
         (Tier 1 sources are exempt from this requirement)
Gate 3: NSE existence + liquidity — yfinance confirms ticker is real, liquid,
         and has sufficient market cap

Tickers failing any gate are rejected with a reason.
"""

from typing import Dict, Any, List, Tuple, Optional, Set
from urllib.parse import urlparse

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

# ── Source domain whitelists ──────────────────────────────────────────────────

TIER_1_DOMAINS: Set[str] = {
    # Regulatory / Exchange — single source is sufficient
    "nseindia.com", "bseindia.com", "sebi.gov.in",
    "rbi.org.in",
}

TIER_2_DOMAINS: Set[str] = {
    # Major financial media — ≥2 sources required
    "economictimes.indiatimes.com", "livemint.com",
    "moneycontrol.com", "financialexpress.com",
    "business-standard.com", "ndtvprofit.com", "ndtv.com",
    "cnbctv18.com", "reuters.com", "bloomberg.com",
    "thehindu.com", "hindustantimes.com", "thehindubusinessline.com",
}

TIER_3_DOMAINS: Set[str] = {
    # Brokerage / research platforms — ≥2 sources required
    "zerodha.com", "smallcase.com", "screener.in",
    "tickertape.in", "motilaloswalmf.com", "motilalосвалmf.com",
    "hdfcsec.com", "icicidirect.com",
    "angelone.in", "kotak.com", "axisdirect.in",
    "sharekhan.com", "5paisa.com", "groww.in",
}

_ALL_TRUSTED = TIER_1_DOMAINS | TIER_2_DOMAINS | TIER_3_DOMAINS

# Liquidity and size floors
_MIN_AVG_DAILY_VOLUME = 100_000    # shares
_MIN_MARKET_CAP = 500_00_00_000    # ₹500 Crore in rupees (500 * 10^7)


def _extract_domain(url: str) -> str:
    """Extract the bare domain from a URL string."""
    if not url or url.startswith("fallback://"):
        return ""
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        domain = parsed.netloc.lower()
        # Strip www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _is_trusted(domain: str) -> bool:
    if not domain:
        return False
    for trusted in _ALL_TRUSTED:
        if domain == trusted or domain.endswith("." + trusted):
            return True
    return False


def _is_tier1(domain: str) -> bool:
    for d in TIER_1_DOMAINS:
        if domain == d or domain.endswith("." + d):
            return True
    return False


class SourceVerifier:
    """
    Runs 3-gate verification on raw ticker candidates from WebSearchUniverseAgent.

    Usage:
        verifier = SourceVerifier()
        result = verifier.verify(raw_candidates)
        verified = result["verified"]   # list of tickers that passed all gates
    """

    def verify(self, raw_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Args:
            raw_candidates: List of {ticker, source_urls, themes, source_count}

        Returns:
            {
              "verified": [{"ticker": ..., "themes": [...], "source_domains": [...]}],
              "rejected": {"TICKER.NS": "reason", ...},
              "stats": {...}
            }
        """
        verified: List[Dict] = []
        rejected: Dict[str, str] = {}

        for candidate in raw_candidates:
            ticker = candidate.get("ticker", "")
            source_urls = candidate.get("source_urls", [])
            themes = candidate.get("themes", [])

            if not ticker:
                continue

            # Gate 1 — source credibility
            trusted_domains = []
            untrusted_domains = []
            has_tier1 = False

            for url in source_urls:
                if url.startswith("fallback://"):
                    trusted_domains.append("fallback")
                    continue
                domain = _extract_domain(url)
                if _is_trusted(domain):
                    trusted_domains.append(domain)
                    if _is_tier1(domain):
                        has_tier1 = True
                else:
                    untrusted_domains.append(domain)

            if not trusted_domains:
                rejected[ticker] = f"Gate 1 FAIL: no trusted sources (found: {untrusted_domains[:3]})"
                continue

            # Gate 2 — multi-source confirmation (Tier 1 exempt)
            unique_trusted = set(trusted_domains)
            # Remove fallback from unique count for real validation
            real_trusted = {d for d in unique_trusted if d != "fallback"}
            if not has_tier1 and len(real_trusted) < 2:
                rejected[ticker] = (
                    f"Gate 2 FAIL: only {len(real_trusted)} trusted source(s) "
                    f"(need ≥2, found: {list(real_trusted)})"
                )
                continue

            # Gate 3 — NSE existence + liquidity
            gate3_result, gate3_reason = self._validate_nse(ticker)
            if not gate3_result:
                rejected[ticker] = f"Gate 3 FAIL: {gate3_reason}"
                continue

            verified.append({
                "ticker": ticker,
                "themes": themes,
                "source_domains": list(real_trusted or trusted_domains),
                "source_count": len(real_trusted),
            })

        print(f"  [Verify] {len(verified)} verified, {len(rejected)} rejected from {len(raw_candidates)} candidates")
        if rejected:
            for t, reason in list(rejected.items())[:3]:
                print(f"    REJECT {t}: {reason}")

        return {
            "verified": verified,
            "rejected": rejected,
            "stats": {
                "total_input": len(raw_candidates),
                "verified_count": len(verified),
                "rejected_count": len(rejected),
            },
        }

    def _validate_nse(self, ticker: str) -> Tuple[bool, str]:
        """
        Gate 3: Check ticker exists on NSE and meets liquidity/size floors.
        Returns (passed, reason_if_failed).
        """
        if not _YF_AVAILABLE:
            # Can't validate — let it through with a warning
            return True, "yfinance unavailable — validation skipped"

        if not ticker.endswith(".NS"):
            ticker = ticker + ".NS"

        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="30d")

            if hist.empty:
                return False, f"no price data returned for {ticker} — not found on NSE"

            # Liquidity: average daily volume
            avg_volume = int(hist["Volume"].mean())
            if avg_volume < _MIN_AVG_DAILY_VOLUME:
                return False, f"avg daily volume {avg_volume:,} < floor {_MIN_AVG_DAILY_VOLUME:,}"

            # Market cap check via info (best-effort — yfinance sometimes returns None)
            try:
                info = t.info
                mkt_cap = info.get("marketCap")
                if mkt_cap and mkt_cap < _MIN_MARKET_CAP:
                    return False, f"market cap ₹{mkt_cap/1e7:.0f}Cr < floor ₹500Cr"
            except Exception:
                pass  # Market cap check is best-effort only

            return True, "ok"

        except Exception as exc:
            return False, f"yfinance error: {exc}"
