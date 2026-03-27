# HMAS v2 — Hierarchical Multi-Agent Investment System
## Complete Architecture & Build Plan

> **Status:** Design-confirmed, ready to build
> **CLI:** Same as v1 — `python run.py scout` / `python run.py portfolio`
> **API:** OpenAI only (gpt-4o-mini / gpt-4o / o3-mini)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Scout Mode — Full Pipeline](#2-scout-mode--full-pipeline)
3. [Portfolio Mode — Full Pipeline](#3-portfolio-mode--full-pipeline)
4. [Agent Specifications](#4-agent-specifications)
5. [Verification Layer](#5-verification-layer)
6. [History & Caching System](#6-history--caching-system)
7. [Data Flow Diagram](#7-data-flow-diagram)
8. [File Structure](#8-file-structure)
9. [Model Tier Assignments](#9-model-tier-assignments)
10. [Output Format](#10-output-format)
11. [Build Order](#11-build-order)

---

## 1. System Overview

### Core Philosophy

**v1 approach:** Fetch all stocks → run analysis agents → synthesize → output.
**v2 approach:** Understand the world first → reason about what matters → focus research → select best.

The system now reasons **top-down**:

```
World state → Macro chain → Relevant themes → Candidate stocks → Deep research → Best 5
```

### What's new vs v1

| Capability | v1 | v2 |
|---|---|---|
| Universe selection | Fixed `scout_universe.txt` | Dynamic via web search, macro-guided |
| Source verification | None | Multi-source + credibility check + yfinance validation |
| Macro reasoning | Scattered across agents | Explicit causal chain agent |
| Per-stock history | None | Persistent cache per ticker, reused if < 7 days |
| Intelligence history | None | Each intel agent has rolling history (30–90 days) |
| Agent memory | None | Every agent reads its own past analysis before running |
| Scout universe | Static 20 tickers | Dynamic, theme-driven, internet-sourced |
| Selection priority | None | Stocks from last 7 days get priority boost |
| Portfolio + Scout link | Separate | Portfolio references scout output |

### No `scout_universe.txt` in v2

The universe is no longer a file you maintain. After macro reasoning identifies themes, a dedicated agent uses web search to find the best current candidates for those themes — validated against credible sources and confirmed on NSE via yfinance. Zero manual maintenance required.

---

## 2. Scout Mode — Full Pipeline

`python run.py scout`

### Phase 0 — Intelligence Gathering *(parallel, 4 agents)*

All 4 agents run simultaneously. Each agent:
- Loads its own rolling history file before running
- Incorporates prior analysis to detect trends (not just today's snapshot)
- Saves updated analysis back to history after each run

```
┌─────────────────────┐  ┌──────────────────────┐
│  NewsIntelAgent     │  │  GlobalMarketsAgent  │
│  India + world      │  │  Indices + flows     │
│  financial news     │  │  FX + yields + VIX   │
│  History: 30 days   │  │  History: 30 days    │
└─────────────────────┘  └──────────────────────┘

┌─────────────────────┐  ┌──────────────────────┐
│  GeopoliticsAgent   │  │  MacroDataAgent      │
│  Wars, OPEC,        │  │  Crude, gold,        │
│  sanctions,         │  │  US CPI, Fed, RBI,   │
│  elections, tariffs │  │  India CPI, bonds    │
│  History: 90 days   │  │  History: 6 months   │
└─────────────────────┘  └──────────────────────┘
```

**Each agent's history structure enables:**
- "Last 3 weeks crude has been rising — not a spike, a trend"
- "FII has been net sellers for 4 consecutive weeks"
- "Geopolitical risk score elevated since [date]"

---

### Phase 1 — Macro Chain Reasoning *(single agent)*

Receives all 4 intelligence packets. Builds an **explicit, step-by-step causal chain** from raw macro inputs to India equity impact.

**Example chain output:**
```
Crude $88 (↑ from $79, OPEC supply restraint)
  → energy import bill rises → India CAD widens
  → INR under pressure (USD/INR: 84.2 → 85.5 expected)
  → RBI cannot cut rates (inflation re-accelerating)
  → bond yields sticky (10Y India: 7.1%)
  → equity PE compression (Nifty fair value drops ~8%)
  → WINNERS: IT exporters (INR weakness = rupee revenue boost),
             Pharma exporters (same INR tailwind),
             Gold (USD-denominated, inflation hedge)
  → LOSERS:  Banking (NIM pressure, PE compress),
             Real Estate (rate-sensitive),
             NBFCs (cost of funds rises)
```

**Outputs:**
- `causal_chain`: step-by-step reasoning in plain English
- `market_regime`: `risk-on` / `risk-off` / `mixed` / `sector-rotation`
- `explore_themes`: list of sectors/assets to focus on (e.g., `["IT", "Pharma", "Gold ETF"]`)
- `avoid_themes`: sectors to skip (e.g., `["Banking", "Real Estate", "NBFC"]`)
- `india_specific`: rupee outlook, FII sentiment, RBI stance, PE impact
- `regime_confidence`: high / medium / low

---

### Phase 2 — Dynamic Universe via Web Search *(single agent + verification)*

**No fixed ticker list. The agent discovers candidates from the internet.**

#### 2A — WebSearchUniverseAgent

Receives `explore_themes` from Phase 1. Crafts targeted search queries per theme:

```
Theme: "IT exports"
→ Query 1: "best NSE IT stocks analyst picks March 2025 FII buying"
→ Query 2: "top Indian IT midcap stocks strong dollar beneficiary 2025"

Theme: "Gold ETF"
→ Query 1: "best gold ETF NSE India highest liquidity 2025"

Theme: "Pharma exports"
→ Query 1: "top NSE pharma export stocks analyst upgrades Q4 2025"
```

Extracts: company names + NSE ticker symbols from results.
Tags each result with its source URL and domain.

#### 2B — SourceVerificationAgent

This is the trust layer. A candidate ticker must pass **all three gates**:

**Gate 1 — Source Credibility Check**

Only accept tickers from whitelisted credible domains:

```
TIER 1 (highest trust):
  nseindia.com, bseindia.com, sebi.gov.in

TIER 2 (trusted financial media):
  economictimes.indiatimes.com
  livemint.com
  moneycontrol.com
  financialexpress.com
  business-standard.com
  ndtvprofit.com / ndtv.com/business
  cnbctv18.com
  reuters.com
  bloomberg.com

TIER 3 (trusted brokerage/research):
  zerodha.com / smallcase.com
  screener.in / tickertape.in
  motilaloswalmf.com
  hdfcsec.com / icicidirect.com / angelone.in
  kotak.com / axisdirect.in

REJECTED (not accepted):
  reddit.com, twitter.com/x.com, quora.com,
  unknown blogs, telegram channels, WhatsApp forwards,
  any domain not in Tier 1/2/3
```

**Gate 2 — Multi-Source Confirmation**

A ticker must appear in results from **at least 2 independent sources** to advance.
Single-source mentions are flagged as `unconfirmed` and dropped.

*Exception: If the source is Tier 1 (NSE/BSE/SEBI), one source is sufficient.*

**Gate 3 — NSE Existence + Liquidity Validation**

For each surviving ticker:
1. Append `.NS` if not present
2. Fetch last 30 days of price data via yfinance
3. **Fail** if: no data returned (ticker doesn't exist on NSE)
4. **Fail** if: average daily volume < 100,000 shares (illiquid, avoid)
5. **Fail** if: market cap < ₹500 Cr (micro-cap, too risky for retail)
6. **Pass** otherwise — ticker is real, liquid, tradeable

**Final output:** `verified_candidates: ["TCS.NS", "INFY.NS", "LTIM.NS", "GOLDBEES.NS", ...]`
Typically 8–15 verified candidates proceed to Phase 3.

---

### Phase 3 — Stock Deep Dive *(parallel, one agent per candidate)*

Each `StockResearchAgent(ticker)` runs independently.

**History check first:**
```
Load data/stock_history/{ticker}.json
  If last_analysis_date < 7 days ago:
    → Load previous analysis as base context
    → Only refresh: latest price, last 3 days news, updated technicals
    → Full fundamentals from cache (earnings don't change weekly)
  Else:
    → Full fresh analysis
```

**Research gathered per stock:**

| Dimension | Data Points |
|---|---|
| **Recent News** | Last 14 days company + sector headlines (via Tavily/news MCP) |
| **Technicals** | RSI (14), MACD, MA50/MA200, volume profile, 52W high/low position, support/resistance levels |
| **Fundamentals** | PE ratio (vs sector avg), PB ratio, ROE, D/E ratio, revenue growth (YoY), earnings trend (last 4 quarters), promoter holding % |
| **Quant** | 1M/3M/6M price momentum, beta, volatility (30-day), relative strength vs Nifty |
| **Macro alignment** | Explicit: "given the current regime (from Phase 1), how does this stock benefit or get hurt?" |

**Output per stock — the "full story":**
```json
{
  "ticker": "INFY.NS",
  "story": "Infosys stands out in a dollar-strength regime...[full narrative]",
  "opportunity_type": "macro_tailwind",
  "entry_zone": "1,820 – 1,850",
  "stop_loss": "1,740 (below 200-DMA)",
  "time_horizon": "6–8 weeks",
  "conviction": "high",
  "key_risk": "Weak Q4 guidance could invalidate the setup",
  "technicals_summary": "RSI 58, above MA50, MACD bullish crossover",
  "fundamentals_summary": "PE 22x (below 5Y avg 25x), ROE 31%, strong balance sheet",
  "macro_alignment": "direct beneficiary: INR weakness adds ~3–4% to USD revenue in rupee terms",
  "news_highlights": ["TCS, Infosys both see deal wins in BFSI segment", "..."],
  "score": 82
}
```

Story is saved to `data/stock_history/{ticker}.json` with timestamp.

---

### Phase 4 — Selection & Ranking *(single agent)*

`SelectionAgent` receives all stock stories and:

1. **Scores each stock** across 4 dimensions (weighted):
   - Macro alignment: 30%
   - Fundamental quality: 25%
   - Technical setup: 25%
   - Momentum/quant: 20%

2. **Priority boost:** Check `data/scout_history.json`
   - If ticker appeared in last 7 days' selections → +10 score bonus
   - Rationale: a strong setup that was identified last week is likely still valid; don't lose the thread

3. **Selects Top 5** by final score

4. **Saves to** `data/scout_history.json`:
   ```json
   {
     "2025-03-27": ["INFY.NS", "TCS.NS", "GOLDBEES.NS", "SUNPHARMA.NS", "LTIM.NS"],
     "2025-03-20": ["INFY.NS", "HCLTECH.NS", "GOLDBEES.NS", "DRREDDY.NS", "BHARTIARTL.NS"]
   }
   ```

5. **Final output:** Top 5 ranked opportunities with full stories + market brief

---

## 3. Portfolio Mode — Full Pipeline

`python run.py portfolio`

### Phase 0 + 1 — Macro Intelligence + Chain Reasoning

**Identical to Scout Phases 0 and 1.**

If scout was run within the last 2 hours, the macro chain output is reused from cache (`data/intel_history/macro_chain_cache.json`) — no redundant API calls.

---

### Phase 2 — Holding Deep Dive *(parallel, one agent per holding)*

`HoldingResearchAgent(ticker, holding_data)` for each portfolio holding.

**History check:** Same 7-day cache logic as StockResearchAgent. If scout already researched this ticker today, that analysis is reused as the base — only P&L context is layered on top.

**Research gathered:**
Same dimensions as StockResearchAgent (news, technicals, fundamentals, quant, macro alignment) PLUS:

| Addition | Details |
|---|---|
| **P&L context** | Entry price, current price, % unrealized P&L, days held |
| **Thesis validation** | Does current data confirm or contradict the original reason for buying? |
| **Blank-slate test** | "If I had zero exposure today, would a fresh buyer initiate at current price/data?" |
| **Exit condition check** | Is the user-defined exit condition close to being triggered? |

**Output per holding:**
```json
{
  "ticker": "RELIANCE.NS",
  "action": "HOLD",
  "narrative": "Reliance benefits from the current macro regime...[full story]",
  "thesis_status": "intact",
  "blank_slate_test": "PASS",
  "macro_alignment": "neutral — domestic business insulated, O2C segment headwind from crude spike",
  "entry": 2450.0,
  "current": 2610.0,
  "pnl_pct": 6.5,
  "exit_condition_status": "not triggered",
  "key_risk": "Crude above $95 would hurt O2C margins significantly",
  "technicals_summary": "RSI 61, above MA50 and MA200, consolidating near all-time high"
}
```

---

### Phase 3 — Portfolio Synthesis *(single agent)*

`PortfolioAdvisorAgent` receives all holding stories + macro chain + (optionally) today's scout top 5.

**Produces:**
1. **Per-holding action:** `HOLD / ADD / TRIM / EXIT` with full reasoning chain
2. **Macro overlay:** "Your holdings that benefit most from current regime: X, Y. Most exposed to downside: Z."
3. **Concentration check:** "3 of your 5 holdings are rate-sensitive — if RBI holds longer, this creates correlated downside."
4. **Opportunity cross-reference:** "Scout found INFY.NS (high conviction IT play). You have no IT exposure — consider if this fits your risk appetite."
5. **Anti-sunk-cost flag:** Any holding that fails the blank-slate test is called out explicitly with the P&L and a clear "sunk cost bias" warning — not softened.

---

## 4. Agent Specifications

### Intelligence Agents (Phase 0)

| Agent | Input | History File | Key Signals |
|---|---|---|---|
| `NewsIntelAgent` | India + world RSS, Tavily | `news_intel.json` (30d) | Corporate events, earnings, regulatory moves, sector news |
| `GlobalMarketsAgent` | yfinance: ^GSPC, ^NDX, ^N225, ^HSI, ^GDAXI, DX-Y.NYB, USDINR=X | `global_markets.json` (30d) | Index directions, DXY trend, USD/INR, FII/DII flows, VIX level |
| `GeopoliticsAgent` | World news MCP, Tavily geopolitical queries | `geopolitics.json` (90d) | OPEC decisions, wars/ceasefires, sanctions, elections, tariffs |
| `MacroDataAgent` | yfinance commodities + macro MCP | `macro_data.json` (6m) | Brent crude, gold, US 10Y yield, India 10Y yield, CPI trends, RBI/Fed stance |

### Reasoning Agents (Phase 1–2)

| Agent | Input | Output |
|---|---|---|
| `MacroChainAgent` | All 4 intel packets + their histories | Causal chain, regime, explore/avoid themes, India overlay |
| `WebSearchUniverseAgent` | `explore_themes` from MacroChain | Raw candidate list with source URLs |
| `SourceVerificationAgent` | Raw candidates + source URLs | Verified candidates (passed all 3 gates) |

### Research Agents (Phase 3)

| Agent | Input | Output |
|---|---|---|
| `StockResearchAgent(ticker)` | Verified ticker + macro chain + live data | Full story JSON, saved to stock history |
| `HoldingResearchAgent(ticker, holding)` | Holding data + macro chain + live data | Action recommendation JSON |

### Synthesis Agents (Phase 4)

| Agent | Input | Output |
|---|---|---|
| `SelectionAgent` | All stock stories + scout history | Top 5 ranked with full stories + updated scout_history.json |
| `PortfolioAdvisorAgent` | All holding stories + macro chain + scout top 5 | Per-holding actions + portfolio-level advice |

---

## 5. Verification Layer

Full detail on the 3-gate verification for web-sourced tickers.

### Gate 1 — Source Credibility

```python
TRUSTED_DOMAINS = {
    # Tier 1 — Regulatory / Exchange (single source sufficient)
    "nseindia.com", "bseindia.com", "sebi.gov.in",

    # Tier 2 — Major Financial Media
    "economictimes.indiatimes.com", "livemint.com",
    "moneycontrol.com", "financialexpress.com",
    "business-standard.com", "ndtvprofit.com",
    "cnbctv18.com", "reuters.com", "bloomberg.com",
    "thehindu.com", "hindustantimes.com",

    # Tier 3 — Brokerage / Research Platforms
    "zerodha.com", "smallcase.com", "screener.in",
    "tickertape.in", "motilaloswalmf.com",
    "hdfcsec.com", "icicidirect.com",
    "angelone.in", "kotak.com", "axisdirect.in",
    "sharekhan.com", "5paisa.com",
}
```

Any ticker mentioned only on untrusted domains is dropped immediately, regardless of how confident it sounds.

### Gate 2 — Multi-Source Confirmation

- Ticker must appear in results from **≥ 2 different trusted domains**
- Tier 1 sources are exempt (NSE listing = ground truth)
- Track: `{ticker: [source1_domain, source2_domain, ...]}`

### Gate 3 — NSE Existence + Liquidity

```
For each candidate ticker:
  1. Ensure .NS suffix
  2. yfinance.Ticker(ticker).history(period="30d")
  3. REJECT if: empty dataframe (not on NSE)
  4. REJECT if: avg_daily_volume < 100,000 shares
  5. REJECT if: market_cap < ₹500 Cr
  6. ACCEPT otherwise
```

### Verification Output

```json
{
  "verified": ["INFY.NS", "TCS.NS", "GOLDBEES.NS"],
  "rejected": {
    "XYZ.NS": "not found on NSE",
    "SMALLCAP123.NS": "avg volume 42,000 — below liquidity floor",
    "SOMECO.NS": "only found on 1 source (moneycontrol.com)"
  },
  "verification_timestamp": "2025-03-27T10:30:00"
}
```

---

## 6. History & Caching System

### Directory structure

```
data/
  intel_history/
    news_intel.json          ← 30-day rolling window (auto-pruned)
    global_markets.json      ← 30-day rolling window
    geopolitics.json         ← 90-day rolling window
    macro_data.json          ← 6-month rolling window
    macro_chain_cache.json   ← Last macro chain output (2-hour TTL)

  stock_history/
    HDFCBANK.NS.json         ← Last full analysis for this ticker
    INFY.NS.json
    RELIANCE.NS.json
    ...                      ← One file per ticker, created on first research

  scout_history.json         ← Selection log: date → [top 5 tickers]
```

### Intel agent history format

```json
{
  "agent": "GlobalMarketsAgent",
  "entries": [
    {
      "date": "2025-03-27",
      "summary": "S&P500 -1.2% on week, DXY at 104.5 (3-week high), USD/INR 84.8, VIX 18.2...",
      "key_signals": ["DXY strengthening", "FII net sellers ₹2,100Cr this week", "Nifty -0.8%"],
      "regime": "risk-off"
    },
    ...
  ],
  "trend_summary": "DXY has strengthened 3 consecutive weeks. FII net sellers for 4 weeks. Risk-off tone persisting."
}
```

The `trend_summary` field is updated on each run — the agent reads the last 4 weeks of entries and summarizes the trend. This is what gets passed to `MacroChainAgent` so it has multi-week context.

### Stock history format

```json
{
  "ticker": "INFY.NS",
  "last_updated": "2025-03-27T10:45:00",
  "story": "Infosys is positioned as a direct beneficiary...[full narrative]",
  "score": 82,
  "entry_zone": "1,820–1,850",
  "stop_loss": "1,740",
  "time_horizon": "6–8 weeks",
  "conviction": "high",
  "fundamentals": {
    "pe": 22.1,
    "pb": 6.8,
    "roe": 31.2,
    "revenue_growth_yoy": 8.4,
    "promoter_holding": 14.9
  },
  "technicals": {
    "rsi_14": 58,
    "above_ma50": true,
    "above_ma200": true,
    "macd_signal": "bullish_crossover"
  }
}
```

### Cache TTL rules

| Cache | TTL | Reason |
|---|---|---|
| Intel agent history | Rolling window, never expires | Trends build over time |
| `macro_chain_cache.json` | 2 hours | Portfolio run after scout reuses it |
| Stock history | 7 days | Fundamentals/thesis don't change daily |
| Scout history | Permanent (pruned after 30 days) | Selection memory for priority boost |

---

## 7. Data Flow Diagram

### Scout Mode

```
                    ┌─────────────────────────────────────────────────┐
PHASE 0             │           INTELLIGENCE GATHERING                │
(parallel)          │  NewsIntel  GlobalMarkets  Geopolitics  MacroData │
                    │    +hist        +hist          +hist        +hist  │
                    └─────────────────────┬───────────────────────────┘
                                          │ 4 intel packets
                    ┌─────────────────────▼───────────────────────────┐
PHASE 1             │           MACRO CHAIN REASONING                 │
                    │  "crude $88 → CAD widens → RBI stuck → PE down" │
                    │  regime: risk-off  explore: [IT, Gold, Pharma]  │
                    │  avoid: [Banking, Realty]                       │
                    └─────────────────────┬───────────────────────────┘
                                          │ themes + chain
                    ┌─────────────────────▼───────────────────────────┐
PHASE 2A            │          WEB SEARCH UNIVERSE AGENT              │
                    │  2–3 targeted queries per explore_theme         │
                    │  → raw candidates with source URLs              │
                    └─────────────────────┬───────────────────────────┘
                                          │ raw candidates
                    ┌─────────────────────▼───────────────────────────┐
PHASE 2B            │           SOURCE VERIFICATION                   │
                    │  Gate 1: source credibility whitelist           │
                    │  Gate 2: ≥2 independent sources                 │
                    │  Gate 3: NSE existence + liquidity check        │
                    └─────────────────────┬───────────────────────────┘
                                          │ 8-15 verified candidates
          ┌─────────┬───────────┬─────────▼──────────┬─────────────┐
PHASE 3   │Stock    │ Stock     │  Stock             │  Stock      │
(parallel)│Research │ Research  │  Research    ...   │  Research   │
          │INFY.NS  │ TCS.NS    │  GOLDBEES.NS       │  SUNPH.NS   │
          │+history │ +history  │  +history          │  +history   │
          └────┬────┴─────┬─────┴──────────┬─────────┴──────┬──────┘
               │          │                │                 │
               └──────────┴────────────────┴─────────────────┘
                                          │ 8-15 stock stories
                    ┌─────────────────────▼───────────────────────────┐
PHASE 4             │              SELECTION AGENT                    │
                    │  Score: macro(30%) + fundamental(25%)           │
                    │          technical(25%) + quant(20%)            │
                    │  Priority boost: in scout_history last 7 days   │
                    │  → TOP 5  →  save to scout_history.json        │
                    └─────────────────────┬───────────────────────────┘
                                          │
                              ┌───────────▼───────────┐
OUTPUT                        │  Market Brief +       │
                              │  Top 5 Opportunities  │
                              │  (full story each)    │
                              └───────────────────────┘
```

### Portfolio Mode

```
PHASE 0+1   Same as Scout (reuse macro chain cache if < 2 hours)
                                          │
          ┌─────────┬───────────┬─────────▼──────────┬─────────────┐
PHASE 2   │Holding  │ Holding   │  Holding           │  Holding    │
(parallel)│Research │ Research  │  Research    ...   │  Research   │
          │RELI.NS  │ GOLDBEES  │  BHARTI.NS         │  ...        │
          │+P&L ctx │ +P&L ctx  │  +P&L ctx          │             │
          └────┬────┴─────┬─────┴──────────┬─────────┴─────────────┘
               └──────────┴────────────────┘
                                          │ holding stories
                    ┌─────────────────────▼───────────────────────────┐
PHASE 3             │           PORTFOLIO ADVISOR AGENT               │
                    │  Per holding: HOLD/ADD/TRIM/EXIT                │
                    │  Macro overlay + concentration check            │
                    │  Scout cross-reference                          │
                    │  Anti-sunk-cost (blank slate test)             │
                    └─────────────────────┬───────────────────────────┘
                                          │
                     ┌────────────────────▼──────────────────────────┐
OUTPUT               │  Market Brief + Action per Holding +          │
                     │  Portfolio-level view                         │
                     └───────────────────────────────────────────────┘
```

---

## 8. File Structure

```
Investment agents/
│
├── run.py                          ← CLI (unchanged interface)
├── scout_universe.txt              ← DEPRECATED (kept as fallback only)
├── portfolio_memory.json           ← Portfolio holdings (unchanged)
├── ARCHITECTURE_V2.md              ← This document
│
├── data/                           ← NEW: persistent history + cache
│   ├── intel_history/
│   │   ├── news_intel.json
│   │   ├── global_markets.json
│   │   ├── geopolitics.json
│   │   ├── macro_data.json
│   │   └── macro_chain_cache.json
│   ├── stock_history/
│   │   └── {TICKER}.NS.json        ← one file per researched ticker
│   └── scout_history.json
│
├── src/
│   ├── intelligence/               ← NEW: Phase 0 agents
│   │   ├── __init__.py
│   │   ├── base_intel_agent.py     ← base class: history load/save, trend summary
│   │   ├── news_intel_agent.py
│   │   ├── global_markets_agent.py
│   │   ├── geopolitics_agent.py
│   │   └── macro_data_agent.py
│   │
│   ├── reasoning/                  ← NEW: Phase 1 + 2A
│   │   ├── __init__.py
│   │   ├── macro_chain_agent.py    ← explicit causal chain + regime + themes
│   │   ├── web_search_universe.py  ← Tavily queries → raw candidates
│   │   └── source_verifier.py      ← 3-gate verification
│   │
│   ├── research/                   ← NEW: Phase 3
│   │   ├── __init__.py
│   │   ├── base_research_agent.py  ← base class: history check, data gathering
│   │   ├── stock_research_agent.py ← full story per ticker
│   │   └── holding_research_agent.py ← story + P&L + thesis check per holding
│   │
│   ├── selection/                  ← NEW: Phase 4
│   │   ├── __init__.py
│   │   ├── scout_selection_agent.py   ← top 5 with history priority
│   │   └── portfolio_advisor_agent.py ← per-holding action + portfolio view
│   │
│   ├── history/                    ← NEW: persistence layer
│   │   ├── __init__.py
│   │   ├── intel_history.py        ← rolling history for intel agents
│   │   ├── stock_history.py        ← per-ticker analysis cache (7-day TTL)
│   │   └── scout_history.py        ← selection log (priority boost)
│   │
│   ├── core/
│   │   ├── workflow_v2.py          ← NEW: ScoutWorkflow + PortfolioWorkflow
│   │   ├── workflow.py             ← OLD: kept for scan/watchlist/general
│   │   ├── llm_client.py           ← unchanged
│   │   ├── types.py                ← extended with new output types
│   │   ├── reporter.py             ← extended for new output format
│   │   └── orchestration.py        ← unchanged
│   │
│   ├── agents/                     ← OLD: kept for scan/watchlist backward compat
│   │   ├── layer1/
│   │   ├── layer2/
│   │   └── layer3/
│   │
│   ├── data/
│   │   ├── market_fetcher.py       ← unchanged
│   │   └── news_fetcher.py         ← unchanged
│   │
│   ├── mcp_tools/
│   │   └── mcp_tools.py            ← unchanged
│   │
│   └── memory/
│       └── memory_mcp.py           ← unchanged
```

---

## 9. Model Tier Assignments

| Phase | Agent | Model | Reason |
|---|---|---|---|
| Phase 0 | NewsIntelAgent | `gpt-4o-mini` | Data extraction, summarization |
| Phase 0 | GlobalMarketsAgent | `gpt-4o-mini` | Structured data reading |
| Phase 0 | GeopoliticsAgent | `gpt-4o-mini` | News classification |
| Phase 0 | MacroDataAgent | `gpt-4o-mini` | Indicator parsing |
| Phase 1 | MacroChainAgent | `gpt-4o` | Multi-step causal reasoning |
| Phase 2A | WebSearchUniverseAgent | `gpt-4o-mini` | Query crafting + ticker extraction |
| Phase 2B | SourceVerificationAgent | `gpt-4o-mini` | Rule-based classification |
| Phase 3 | StockResearchAgent | `gpt-4o-mini` (data) + `gpt-4o` (story) | Parallel data gathering → synthesis |
| Phase 3 | HoldingResearchAgent | `gpt-4o-mini` (data) + `gpt-4o` (story) | Same as above + P&L context |
| Phase 4 | SelectionAgent | `o3-mini` | High-accuracy final decision |
| Phase 4 | PortfolioAdvisorAgent | `o3-mini` | High-accuracy final decision |

---

## 10. Output Format

### Scout Output

```
════════════════════════════════════════════════════════════════════════════════
  HMAS v2 — SCOUT MODE  |  2025-03-27 10:45
════════════════════════════════════════════════════════════════════════════════

  MARKET BRIEF
  ────────────────────────────────────────────────────────────────────────────
  Regime: RISK-OFF (medium confidence)

  Macro chain: Crude held above $87 for the third consecutive week as OPEC
  maintained supply discipline. This is feeding through to India's import bill,
  widening the current account deficit and putting the rupee under renewed
  pressure (USD/INR now 84.8, testing resistance). With CPI re-accelerating,
  the RBI has no room to cut — bond yields remain sticky near 7.1%, which
  compresses equity PEs across the board. FII has been a net seller for 4
  consecutive weeks (₹8,400 Cr net outflow MTD).

  Winners in this regime: IT exporters (INR weakness = rupee revenue boost),
  Pharma exporters (same tailwind), Gold (inflation + safe-haven demand).
  Avoid: Banks (NIM pressure + PE compression), Real Estate, NBFCs.

  AGENT DIGEST
  ────────────────────────────────────────────────────────────────────────────
  [Intel]  News         BEARISH  |  FII selling, earnings season mixed
  [Intel]  Mkts         RISK-OFF |  DXY +2% MTD, VIX 18, Nifty -1.4%
  [Intel]  Geo          NEUTRAL  |  No major escalation, OPEC steady
  [Intel]  Macro        BEARISH  |  Crude $87, INR 84.8, RBI on hold
  [L1]     MacroChain   RISK-OFF |  3-step chain confirmed, medium confidence

  THIS WEEK'S TOP 5 OPPORTUNITIES
  ────────────────────────────────────────────────────────────────────────────

  ── INFY.NS  [BUY NOW]  conviction: high ────────────────────────────────────
  Infosys is the cleanest play on the current macro regime. INR weakness
  directly adds ~3–4% to dollar revenue in rupee terms without any operational
  change. The stock is trading at 22x PE — below its 5-year average of 25x —
  offering a margin of safety. RSI at 58 with a MACD bullish crossover suggests
  the technical setup is constructive. Two major deal wins in BFSI were reported
  last week, providing fundamental support independent of the macro tailwind.

  Entry: 1,820–1,850   Stop: 1,740 (below 200-DMA)   Horizon: 6–8 weeks
  Buy trigger: All conditions met — act at open
  Key risk: Weak Q4 guidance or sharp INR reversal above 83.5

  ── GOLDBEES.NS  [WATCH — trigger near]  conviction: medium ─────────────────
  ...
```

### Portfolio Output

```
════════════════════════════════════════════════════════════════════════════════
  HMAS v2 — PORTFOLIO MODE  |  2025-03-27 10:52
════════════════════════════════════════════════════════════════════════════════

  [Same Market Brief as above]

  PORTFOLIO DECISIONS
  ────────────────────────────────────────────────────────────────────────────
  Macro overlay: Your portfolio is net exposed to the risk-off regime.
  HDFCBANK.NS and AXISBANK.NS are the most vulnerable — rate-sensitive in a
  hawkish hold environment. RELIANCE.NS is neutral. No IT/export exposure.

  ── HDFCBANK.NS  [WATCH!]  ──────────────────────────────────────────────────
  P&L: Entry ₹1,620 | Current ₹1,580 | -2.5% | Held 42 days

  The original thesis (rate cut cycle beneficiary) is under pressure. RBI is
  now on hold for longer than expected, and PE compression in banking has been
  consistent for 6 weeks. Blank-slate test: FAIL — a fresh buyer looking at
  NIM headwinds and macro-driven PE compression would not initiate here today.

  [!] Sunk cost bias: You are -2.5% on this position. A fresh buyer would not
  initiate at current data. Exit condition check: not yet triggered, but
  approaching. Recommend reducing position size by 50% and reassessing after
  RBI policy meeting.

  ── RELIANCE.NS  [HOLD]  ──────────────────────────────────────────────────
  ...

  PORTFOLIO-LEVEL VIEW
  ────────────────────────────────────────────────────────────────────────────
  Concentration: 2 of 4 holdings are rate-sensitive — correlated downside risk
  if RBI holds through June. Consider rebalancing toward IT/Pharma.

  Scout cross-reference: INFY.NS (high conviction, BUY NOW) would reduce your
  rate-sensitivity concentration and add macro-aligned exposure.
```

---

## 11. Build Order

Build in this sequence — each step is testable before moving to the next.

### Step 1 — History layer `src/history/`
- `intel_history.py` — load/save/prune rolling history, generate trend summary
- `stock_history.py` — load/save per-ticker analysis, 7-day TTL check
- `scout_history.py` — load/save selection log, 7-day lookback query

### Step 2 — Intelligence agents `src/intelligence/`
- `base_intel_agent.py` — abstract base: load history, run, save history
- `news_intel_agent.py`
- `global_markets_agent.py`
- `geopolitics_agent.py`
- `macro_data_agent.py`
- Test: run all 4 in parallel, verify history files are written

### Step 3 — Macro reasoning `src/reasoning/`
- `macro_chain_agent.py` — causal chain + regime + themes
- Test: feed Phase 0 output, verify chain + explore_themes + avoid_themes

### Step 4 — Web search + verification `src/reasoning/`
- `web_search_universe.py` — Tavily queries per theme → raw candidates
- `source_verifier.py` — 3-gate pipeline
- Test: give themes, verify only credible + liquid NSE tickers come out

### Step 5 — Stock research `src/research/`
- `base_research_agent.py` — history check, data gathering helpers
- `stock_research_agent.py` — full story per ticker
- Test: single ticker, verify full story JSON + history file written

### Step 6 — Holding research `src/research/`
- `holding_research_agent.py` — extends stock research + P&L + thesis check
- Test: single holding with known P&L, verify blank-slate test output

### Step 7 — Selection + Portfolio advisor `src/selection/`
- `scout_selection_agent.py` — scoring + top 5 + history priority + save
- `portfolio_advisor_agent.py` — per-holding action + portfolio view
- Test: feed 10 stock stories, verify top 5 + scout_history.json updated

### Step 8 — New workflow `src/core/workflow_v2.py`
- `ScoutWorkflow.run()` — orchestrates all 4 phases
- `PortfolioWorkflow.run()` — orchestrates portfolio pipeline
- Macro chain cache: reuse if < 2 hours old

### Step 9 — Wire into `run.py`
- `python run.py scout` → `ScoutWorkflow`
- `python run.py portfolio` → `PortfolioWorkflow`
- All other commands unchanged (use old workflow)

### Step 10 — Output formatting
- Extend `reporter.py` for new output types
- Update `print_full_report` for new scout + portfolio output sections

---

## Key Design Decisions (rationale)

| Decision | Why |
|---|---|
| History per intel agent | Weekly snapshots miss multi-week trends that matter most (e.g., FII selling for 4 weeks ≠ just one bad day) |
| Web search for universe | Dynamic, always current, macro-guided — eliminates manual maintenance entirely |
| 3-gate verification | Web search is noisy. Gate 1 cuts noise at source. Gate 2 requires consensus. Gate 3 is ground truth. Together they ensure only real, liquid, credible stocks enter the pipeline. |
| 7-day stock history cache | Fundamentals and thesis don't change daily. Avoids re-calling gpt-4o for the same stock on back-to-back days while keeping technicals fresh. |
| History priority boost for selection | A strong setup identified last week is likely still in play. Continuity matters — don't lose the thread by randomizing each week. |
| o3-mini only for final decisions | Expensive model used only where it matters: final HOLD/ADD/TRIM/EXIT per holding, and final top-5 selection. All data gathering uses gpt-4o-mini. |
| Macro chain cache (2-hour TTL) | Running portfolio immediately after scout reuses the same world-view rather than calling gpt-4o twice for the same analysis. |
| Old workflow kept | `scan`, `watchlist`, `watch`, `general` commands are unchanged and use the old pipeline. No regression. |
