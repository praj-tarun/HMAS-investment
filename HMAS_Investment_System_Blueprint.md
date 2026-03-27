# Hierarchical Multi-Agent Investment System (HMAS)
### Build Blueprint for Claude Code

---

## 1. What This System Does

This system cuts your research and reasoning time by compressing market signals into a focused weekly decision brief. It does **not** make decisions for you. It ensures that when you sit down to review your portfolio, you are reading a structured brief — not starting from scratch.

**Three core functions:**
1. **Research compression** — filters India + global news, market data, and technicals down to what is relevant to *your holdings only*
2. **Pattern recognition** — compares current signals against your 12–24 month portfolio history
3. **Entry/exit flagging** — monitors pre-defined conditions and tells you when a thesis is intact, weakening, or broken

**Final output per holding, every week:**
- Thesis status: Intact / Weakening / Broken
- Flag: Hold / Watch closely / Exit condition approaching
- Key reason: one sentence

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      MCP TOOLS                          │
│  India News │ World News │ Market │ Quant │ Macro │ Memory│
└──────┬──────┴─────┬──────┴───┬────┴───┬───┴──┬────┴──┬───┘
       │            │          │        │      │       │
┌──────▼────────────▼──────────▼────────▼──────▼───────▼───┐
│                     LAYER 1 — AGENTS                      │
│  India Business │ Geopolitical │ Commodity │ Sector        │
│  Quant Agent    │ Portfolio Context                        │
└──────────────────────────┬────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────┐
│                    LAYER 2 — LEADS                        │
│      Macro Lead │ Micro Lead │ Quant Lead                 │
└──────────────────────────┬────────────────────────────────┘
                           │ ← Memory MCP always injected here
┌──────────────────────────▼────────────────────────────────┐
│                  LAYER 3 — CHIEF ORCHESTRATOR             │
│              Hold / Rotate / Exit Decision                │
└──────────────────────────┬────────────────────────────────┘
                           │
                  Weekly Decision Brief
```

---

## 3. MCP Tools — What Each One Does

### 3.1 India News MCP
- **Sources:** Economic Times, Moneycontrol, BSE announcements, RBI press releases, SEBI notifications
- **Cadence:** Event-driven (BSE filings drop intraday, RBI statements are scheduled)
- **Feeds:** India Business Agent, Sector Agent
- **Does NOT feed:** Geopolitical Agent, Commodity Agent directly
- **Key rule:** Raw headlines never reach the Orchestrator. Every signal must be interpreted by a Layer 1 agent first.

### 3.2 World News MCP
- **Sources:** Reuters, Bloomberg, BBC, Financial Times
- **Cadence:** Slower but high systemic impact when it moves
- **Feeds:** Geopolitical Agent, Commodity Agent
- **Does NOT feed:** India Business Agent, Sector Agent directly
- **Key rule:** Each agent must apply an **India relevance filter** as the first step in its chain-of-thought. A US jobs report matters only insofar as it affects Fed rates → dollar-rupee → FII flows. The agent must make that translation explicitly.

### 3.3 Market MCP
- **Data:** NSE/BSE live prices, volume, FII/DII flow data, delivery percentage
- **Feeds:** India Business Agent, Sector Agent
- **Purpose:** Separates "RBI cut rates" (news) from "markets actually responded positively" (price reality). Both matter and they sometimes contradict each other.

### 3.4 Quant MCP
- **Computes:** RSI, MACD, Bollinger Bands, 52-week high/low position
- **Feeds:** Quant Agent only
- **Key rule:** Compute only for your *actual holdings*, not the whole market. The Quant Agent's chain-of-thought is always: "What is the technical posture of what I own?"

### 3.5 Macro MCP
- **Data:** RBI minutes and decisions, Fed decisions, Brent crude, Gold spot price, metals index
- **Feeds:** Geopolitical Agent, Commodity Agent
- **Cadence:** Weekly scheduled, unless RBI/Fed event is imminent — then immediate activation

### 3.6 Memory MCP *(Most Important)*
- **Always active.** Injected into the Chief Orchestrator on every single cycle.
- **Three sections (detailed in Section 6):**
  1. Holdings log (ticker, entry price, entry date, current price, unrealized P&L, one-sentence thesis)
  2. Decision log (date, system recommendation, what you actually did, outcome)
  3. Invalidated thesis log (positions where original thesis no longer holds, even if not sold yet)

---

## 4. Layer 1 — Specialized Agents

### 4.1 India Business Agent
**Tools:** India News MCP + Market MCP

**Chain-of-thought:**
1. Pull latest RBI policy signals, NSE/BSE filings for held stocks
2. Check FII/DII flow direction from Market MCP
3. Ask: *Does this change the earnings or valuation thesis for any holding?*
4. Output a signal packet: data point → historical context (high/low/normal?) → directional implication → uncertainty level

**Output format:** Signal packet, not prose. 3–5 bullet points max.

---

### 4.2 Geopolitical Agent
**Tools:** World News MCP + Macro MCP

**Chain-of-thought:**
1. Identify global events from World News (trade tensions, elections, conflicts, sanctions)
2. Apply India relevance filter: *How does this affect India specifically?* (rupee, FII sentiment, export sectors, oil import bill)
3. Flag events by impact horizon: near-term (1–4 weeks) vs structural (6–18 months)
4. Output directional signal with confidence level

**Output format:** Signal packet. Flag if near-term or structural.

---

### 4.3 Commodity Agent
**Tools:** World News MCP + Macro MCP

**Chain-of-thought:**
1. Pull Brent crude, Gold, and metals prices
2. Translate to Indian context: *What does this level of oil do to India's CAD, inflation, and RBI room to cut?*
3. Cross-check with World News for supply-side reasons (OPEC, geopolitical disruption)
4. Output directional signal for each commodity with specific India inflation implication

**Output format:** Signal packet per commodity with one-line India impact translation.

**Key insight:** Gold rising simultaneously with oil in Indian markets historically signals a flight to safety, not just inflation. Flag this divergence explicitly — do not average it out.

---

### 4.4 Sector Agent
**Tools:** India News MCP + Market MCP

**Covers:** Tech, FMCG, Energy (expand as needed)

**Chain-of-thought:**
1. Pull sector-specific earnings, management commentary, order books from India News
2. Check sector price/volume action from Market MCP
3. Filter only sectors relevant to your current holdings
4. Flag: is the sector's story getting better, worse, or unchanged?

**Output format:** One signal per sector you hold. Thesis intact / weakening / broken.

---

### 4.5 Quant Agent
**Tools:** Quant MCP only

**Chain-of-thought:**
1. Pull RSI, MACD, Bollinger Bands for each holding
2. Note 52-week position: is each holding near highs, lows, or mid-range?
3. Check volume trend: is price movement supported by volume or thin?
4. Output: for each holding, is the technical posture aligned with or contradicting the fundamental thesis?

**Key rule:** The Quant Agent does not have opinions on *why* — only *what the price is doing*. Interpretation happens at the Quant Lead level.

**Output format:** Per holding: RSI level, MACD signal (bullish/bearish cross?), price vs 52-week range, volume note.

---

### 4.6 Portfolio Context Agent
**Tools:** Memory MCP only

**Chain-of-thought:**
1. Load current holdings log from Memory MCP
2. For each holding: what was the original thesis? Is it still the reason you own it?
3. Load decision log: what has the system recommended before, and what actually happened?
4. Flag any position sitting in the "invalidated thesis" log
5. Compute unrealized P&L context: how does the current loss/gain affect risk posture?

**Key output:** A context document injected into every Layer 2 Lead and the Chief Orchestrator. This is what gives the system memory.

---

## 5. Layer 2 — Domain Leads

### 5.1 Macro Lead
**Consolidates:** Geopolitical Agent + Commodity Agent

**Chain-of-thought:**
1. Read both signal packets
2. **Dissent check first:** Do these two signals contradict each other? If yes, flag the contradiction explicitly before synthesizing.
3. Identify dominant narrative: what is the macro environment saying overall?
4. Apply India-specific translation: what does the global macro mean for Indian equity risk premium?
5. Produce a structured scorecard (see format below)

**Scorecard format:**
```
Direction: Bullish / Bearish / Neutral
Confidence: High / Medium / Low
Horizon: Near-term (weeks) / Structural (months)
One-line thesis: [your synthesis]
Dissent flag: [any signal that does NOT fit this narrative]
```

**Critical design rule:** The Dissent Appendix must be written *before* the main thesis. The anomaly is often the alpha.

---

### 5.2 Micro Lead
**Consolidates:** India Business Agent + Sector Agent

**Conflict resolution chain-of-thought** (for cases like: India Business Bullish on RBI policy, but Commodity Agent Bearish on rising oil):

**Step 1 — Causal directionality:**
Are these signals in conflict because they operate on *different time horizons*, or are they genuinely contradictory about the *same future*? RBI policy affects equity valuations over 6–18 months. Rising oil affects margins in 1–3 months. These are not the same bet — they describe a near-term bearish / medium-term bullish posture. That is a specific, actionable conclusion.

**Step 2 — Portfolio exposure mapping:**
Which signal has greater sensitivity to the assets *actually held*? If you're overweight oil-dependent sectors (auto, chemicals, FMCG), then rising oil is a direct earnings threat to current holdings — not a generic macro concern. The conflict resolution must be portfolio-contextualized, not market-generic.

**Step 3 — Asymmetric risk weighting:**
Given capital-preservation posture (after drawdown), a confirmed bearish signal carries 1.5x the weight of an equivalent bullish signal. This is rational risk-adjusted reasoning: the cost of being wrong on the downside exceeds the cost of missing an upside. Hard-code this into the Micro Lead's logic.

**Step 4 — Escalate or synthesize?**
- Signals point to different time horizons with clear portfolio implications → **synthesize**
- Signals are genuinely contradictory about the same near-term outcome with high stakes → **escalate both to Chief Orchestrator with a Priority Flag**

**Scorecard format:** Same as Macro Lead, plus Escalation Flag (Yes/No).

---

### 5.3 Quant Lead
**Consolidates:** Quant Agent output

**Key architectural note:** The Quant Lead is a **calibration layer**, not a parallel reporter. Its output arrives at the Chief Orchestrator as a *modifier* attached to the Macro and Micro reports — not as a third independent opinion.

**Chain-of-thought:**
1. Read Quant Agent signal packets for all holdings
2. Ask: *What is the market price implying about the fundamental thesis the Macro and Micro Leads just presented?*
3. Flag divergences: if Macro Lead says Bullish but Nifty is forming a death cross on declining volume, that divergence must be named explicitly
4. Output: Technical alignment score for each holding (Aligned / Diverging / Conflicted)

**Output format:** Not a standalone report. A modifier document: "Here is what market price is saying about each fundamental signal."

---

## 6. Memory MCP — Detailed Structure

This is the most important component. Build this as a simple structured JSON or markdown document *before writing any agent code*.

### 6.1 Holdings Log
```json
{
  "holdings": [
    {
      "ticker": "RELIANCE.NS",
      "entry_price": 2450,
      "entry_date": "2024-03-10",
      "current_price": 2210,
      "unrealized_pnl_pct": -9.8,
      "thesis": "Energy transition + Jio growth; exit if Jio ARPU growth stalls for 2 consecutive quarters",
      "exit_condition": "Jio ARPU growth stalls 2 consecutive quarters OR crude sustained above $95"
    }
  ]
}
```

### 6.2 Decision Log
```json
{
  "decisions": [
    {
      "date": "2025-01-12",
      "system_recommendation": "Hold — Macro bearish near-term but thesis intact",
      "action_taken": "Held",
      "outcome_30d": "-3.2%",
      "was_recommendation_correct": false,
      "notes": "Macro Lead underweighted oil impact on margins"
    }
  ]
}
```

### 6.3 Invalidated Thesis Log
```json
{
  "invalidated": [
    {
      "ticker": "EXAMPLE.NS",
      "original_thesis": "Rural recovery to drive FMCG volume growth",
      "invalidation_reason": "Rural inflation persistent for 3 quarters; volume growth negative",
      "date_invalidated": "2025-02-01",
      "action_taken": "Still holding — review immediately"
    }
  ]
}
```

---

## 7. Layer 3 — Chief Orchestrator

### 7.1 Inputs (in this order)
1. Memory MCP context (holdings log + decision log + invalidated thesis log)
2. Macro Lead scorecard + dissent flag
3. Micro Lead scorecard + escalation flag
4. Quant Lead calibration modifier

### 7.2 Chain-of-Thought (must follow this sequence)

**Step 1 — Anti-recency check:**
Before reading any current cycle reports, read the 12-month performance context from Memory MCP. Ask: *What has been true over 12 months? What changed in the last 30 days? Is the recent change a regime shift or noise within the existing regime?*

**Step 2 — Thesis validation per holding:**
For each holding, cross-reference the current signals against the original thesis in the Holdings Log. Ask: *Is the reason I bought this still valid today?*

**Step 3 — Blank Slate Test (anti-sunk-cost):**
Before issuing a Hold recommendation, ask: *"If I had zero exposure to this asset today, with only the current data, would I initiate a new position?"*
- If Yes → Hold is legitimate
- If No → This is a sunk cost hold. Flag it explicitly. The investor must see this named honestly.

**Step 4 — Conflict resolution (if Micro Lead escalated a Priority Flag):**
Use Macro Lead context to break the tie. Macro context takes precedence over Micro context in cases of genuine conflict about the same near-term outcome.

**Step 5 — Produce decision brief**

### 7.3 Decision Brief Format (per holding)
```
TICKER: [name]
Thesis status: Intact / Weakening / Broken
Technical alignment: Aligned / Diverging / Conflicted
Flag: HOLD / WATCH / EXIT CONDITION APPROACHING
Reason: [one sentence — the single most important thing driving this flag]
Blank slate test: PASS / FAIL (if FAIL, note it)
```

---

## 8. Conditional Activation Logic

Run the full system only when needed. This cuts token costs by ~60%.

| Trigger | Tools activated | Agents activated |
|---|---|---|
| Scheduled weekly review | All tools | Full system |
| RBI / Fed announcement | Macro MCP, India/World News | Macro Lead only |
| Holding moves ±3% intraday | Market MCP, Quant MCP | Quant Agent + relevant Sector Agent |
| Major geopolitical event | World News MCP, Macro MCP | Geopolitical + Macro Lead |
| You manually flag a holding | Memory MCP + relevant tools | Targeted agents only |
| Commodity spike (oil ±5%) | Macro MCP, World News MCP | Commodity Agent + Macro Lead |

---

## 9. Information Bottleneck Safeguards

These are the three places the system will lose critical data without explicit protection.

### 9.1 Dissent Appendix (Macro Lead)
Every Domain Lead report must include a `dissent` field — signals that did NOT fit the dominant narrative. The Chief Orchestrator reads this field *before* the main thesis. Anomalies are often the most valuable signals.

### 9.2 Contradiction Detection Gate (Micro Lead)
Before synthesizing, the Micro Lead must explicitly ask: *"Does any single-agent signal, if true, invalidate the overall narrative I am about to report?"* If yes → Priority Flag to Orchestrator, not averaged out.

### 9.3 Quant Lead as Calibrator (not a third vote)
The Quant Lead output is a modifier, not a third opinion. If Macro + Micro say Bullish but price/volume says otherwise, the Quant Lead must name that divergence. Never treat technical signals as a separate parallel vote — they are the market's real-time verdict on your fundamental thesis.

---

## 10. Build Sequence (Recommended Order)

### Phase 0 — Before any code
1. Create the Memory MCP document manually (Holdings Log + Decision Log)
2. Write a one-sentence thesis and explicit exit condition for every holding you own
3. Write the Invalidated Thesis Log — be honest about positions where the original reason is gone

> This document becomes the brain of your entire system. Without it, agents have nothing real to reason against.

### Phase 1 — Single agent (validate before scaling)
Build only the India Business Agent + Market MCP connection. Ask it weekly: *"Given this data, is my thesis for each holding still intact?"* Run for 2–4 weeks. Evaluate if it adds value before adding more agents.

### Phase 2 — Add World News + Geopolitical
Add the split news architecture. Validate that India News and World News are staying in their correct lanes — India News not confusing Geopolitical agent, World News not distracting India Business agent.

### Phase 3 — Add Quant Agent
Connect Quant MCP. Validate that it's computing signals only for your holdings, not doing a general market scan.

### Phase 4 — Build Layer 2 Leads
Implement Macro Lead first (easier synthesis). Then Micro Lead with the full conflict resolution chain-of-thought. Then Quant Lead as calibration layer.

### Phase 5 — Chief Orchestrator
Implement the full chain-of-thought sequence: anti-recency check → thesis validation → blank slate test → conflict resolution → brief output.

### Phase 6 — Conditional activation
Add trigger logic so not all agents run on every cycle.

---

## 11. LangGraph Implementation Notes

### Node design
- Each Layer 1 agent = one LangGraph node
- Each Layer 2 Lead = one LangGraph node
- Chief Orchestrator = one LangGraph node
- Memory MCP = state object passed through the graph, not a node

### State object
The LangGraph state should carry:
```python
{
  "portfolio_context": {},       # from Memory MCP — always loaded first
  "agent_signals": {},           # Layer 1 outputs (signal packets)
  "lead_scorecards": {},         # Layer 2 outputs (structured scorecards)
  "dissent_flags": [],           # collected across all Leads
  "priority_escalations": [],    # from Micro Lead conflict detection
  "decision_brief": {}           # final output
}
```

### Token cost reduction
- Agents produce **signal packets** (structured JSON), not prose essays
- Domain Leads produce **structured scorecards** (fixed schema), not narrative reports
- Only the Chief Orchestrator produces prose — and only for the final brief
- Use conditional edges in LangGraph to skip agents that have no active trigger

### Model recommendation
- Layer 1 agents: cheaper/faster model (Haiku) — they are doing filtering, not reasoning
- Layer 2 Leads: mid-tier model (Sonnet) — they are doing synthesis and conflict detection
- Chief Orchestrator: best model available — this is where the final reasoning lives

---

## 12. Key Design Principles (Never Violate These)

**1. Preserve contradiction.**
A system that achieves consensus too easily is an expensive echo chamber. Every layer must actively resist premature consensus. The Dissent Appendix, Contradiction Detection Gate, and Blank Slate Test all serve this principle.

**2. Contextualize to portfolio, not market.**
Agents will naturally reason about "the market." Your system's value is reasoning about *your specific holdings* within that market. Every signal must be filtered through your actual positions, cost basis, time horizon, and capital preservation mandate. A macro insight irrelevant to your allocation is noise.

**3. Name the bias before acting on it.**
The -10% drawdown is a psychological load that will distort outputs toward panic selling or sunk cost holding depending on how prompts are structured. The only defense is to make the bias explicit, visible, and named in the reasoning chain. A system that reasons *around* the loss is compromised. A system that reasons *through* it — by naming it and testing it against current fundamentals — is trustworthy.

**4. The system supports decisions. It does not make them.**
The Chief Orchestrator produces a defensible, well-reasoned recommendation. The final judgment is always yours.

---

## 13. Quick Reference — Tool-to-Agent Map

| Tool | Feeds agents | Does NOT feed |
|---|---|---|
| India News MCP | India Business, Sector | Geopolitical, Commodity |
| World News MCP | Geopolitical, Commodity | India Business, Sector |
| Market MCP | India Business, Sector | Quant Agent |
| Quant MCP | Quant Agent only | All others |
| Macro MCP | Geopolitical, Commodity | India Business, Sector |
| Memory MCP | Portfolio Context + Chief Orchestrator (always) | Bypassed by no one |

---

## 14. Quick Reference — Agent Output Formats

| Agent | Output type | Max length |
|---|---|---|
| India Business | Signal packet (JSON) | 5 bullets |
| Geopolitical | Signal packet (JSON) | 5 bullets + horizon tag |
| Commodity | Signal packet per commodity | 3 bullets + India impact |
| Sector | Signal per held sector | 3 bullets |
| Quant Agent | Per-holding technical data | Structured JSON |
| Portfolio Context | Context document | Holdings log + flags |
| Macro Lead | Structured scorecard | Fixed schema + dissent |
| Micro Lead | Structured scorecard | Fixed schema + escalation flag |
| Quant Lead | Calibration modifier | Alignment score per holding |
| Chief Orchestrator | Decision brief | Per-holding, one paragraph |

---

*Built for an individual investor managing an Indian equity portfolio. Designed for capital preservation posture with opportunistic rotation. All agent reasoning is advisory — final investment decisions remain with the investor.*
