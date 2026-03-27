# HMAS Investment — Hierarchical Multi-Agent Investment System

A multi-agent AI system for Indian equity portfolio analysis. Runs a 4-phase pipeline every week to give you practical, forward-looking guidance on your holdings — not just a market summary.

---

## What it does

**Portfolio mode** — reviews each holding you own:
- Thesis intact / weakening / broken check
- Recovery path math (how far to breakeven, what conditions unlock it)
- Specific buy/add signal and exit signal per holding
- Gold hedge analysis (trim/hold GOLDBEES)
- 30-day IF/THEN action checklist

**Scout mode** — finds the week's best opportunities:
- Macro-guided universe discovery via web search
- Scores 10-15 stocks on macro alignment, fundamentals, technicals, momentum
- Returns Top 5 with entry zone, stop loss, time horizon

**Simulation tab** — tracks recommendation accuracy over time, shows what-if P&L.

---

## Architecture

```
Phase 0  4 Intel Agents (parallel)   News · Global Markets · Geopolitics · Macro Data
Phase 1  Macro Chain Agent            Causal chain → regime → explore/avoid themes
Phase 2  Research Agents (parallel)  Per-holding deep dive OR stock universe research
Phase 3  Advisor / Selector           Portfolio synthesis OR Top-5 selection
```

Models: `gpt-4o-mini` (layer 1, fast filtering) · `gpt-4o` (layer 2, synthesis) · `o3-mini` (layer 3, final reasoning)

Each run learns from the previous run — previous regime, recommendations, and P&L context are passed back into the agents.

---

## Setup

**Requirements:** Python 3.10+, OpenAI API key, optional Tavily API key (web search for Scout mode)

```bash
git clone https://github.com/YOUR_USERNAME/hmas-investment.git
cd hmas-investment
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set OPENAI_API_KEY and optionally TAVILY_API_KEY
```

---

## Usage

```bash
# Add your holdings
python run.py add GOLDBEES.NS

# Or sync from broker xlsx statement
python run.py sync-holdings          # put xlsx files in holdings/ folder

# Run weekly portfolio review
python run.py portfolio

# Find new opportunities
python run.py scout

# Dashboard (recommended)
streamlit run dashboard.py
```

---

## Dashboard

```bash
streamlit run dashboard.py
```

Three tabs:
- **Portfolio** — run analysis, view holding cards with buy/exit signals, 30-day checklist
- **Scout** — run scout, view top picks with entry/stop/horizon
- **Simulation** — tracks how accurate past recommendations were

---

## Project Structure

```
run.py                  CLI entry point
dashboard.py            Streamlit dashboard
requirements.txt
.env.example            API key template

src/
  core/
    llm_client.py       OpenAI API wrapper (layer1/2/3 routing)
    workflow_v2.py      Scout + Portfolio pipeline orchestration
    report_history.py   Per-mode JSON archive + previous context for learning
    types.py            Shared dataclasses (HoldingAction, MacroChainOutput, ...)
  intelligence/         Phase 0: 4 intel agents
  reasoning/            Phase 1: macro chain + web universe
  research/             Phase 2: stock + holding research agents
  selection/            Phase 3: scout selection + portfolio advisor
  memory/               Portfolio state (holdings, watchlist)
  data/                 Market data fetchers, holdings xlsx importer
  history/              7-day stock analysis cache (shared between modes)

holdings/               Put broker xlsx statements here (gitignored)
reports/                Generated reports (gitignored)
```
