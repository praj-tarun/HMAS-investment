# HMAS — Claude Chat Analysis Chain
### A 4-Prompt Chain to Replicate the Full Investment Analysis Pipeline

---

## HOW TO USE THIS

1. Open a **fresh Claude chat** at claude.ai
2. Paste **Prompt A** first — fill in your portfolio and market data
3. After Claude acknowledges, paste **Prompt B** as-is (no edits needed)
4. After Claude finishes B, paste **Prompt C** as-is
5. After Claude finishes C, paste **Prompt D** as-is

**Critical:** Keep all 4 prompts in **one conversation**. Claude carries context forward.
Never start a new chat mid-chain — you'll lose all prior analysis.

---

## DATA YOU NEED BEFORE STARTING

Gather this before Prompt A (takes ~10 minutes):

**For each holding:**
- Current price and today's % change (NSE / broker app)
- Volume (NSE or TradingView)
- RSI, MACD line, MACD signal, MACD histogram (TradingView → any indicator panel)
- Bollinger Bands: Upper, Middle, Lower (TradingView)
- 52-week High and Low (NSE website or broker)
- FII/DII flow for that stock if available (NSE website → FII/DII data)

**Macro data:**
- Brent Crude price in USD (TradingView: UKOIL)
- Gold price in USD (TradingView: GOLD)
- USD/INR rate
- US 10Y Treasury yield (TradingView: US10Y)

**News (this week):**
- 3–5 India headlines (Economic Times, ET Markets, Moneycontrol, SEBI notices)
- 2–3 global headlines relevant to India (Reuters, BBC Business)

---

---

# PROMPT A — Portfolio Context + Market Data

> **COPY AND PASTE THIS ENTIRE BLOCK. Replace everything in [ ] with your real data.**

```
You are acting as my investment analysis system for Indian equities.
I will walk you through a structured 4-step analysis in this conversation.
Do not begin any analysis yet — just acknowledge and confirm you're ready.

════════════════════════════════════════
MY PORTFOLIO
════════════════════════════════════════

[HOLDING 1]
Ticker:          [e.g. RELIANCE.NS]
Entry price:     ₹[e.g. 2400]
Entry date:      [YYYY-MM-DD]
Current price:   ₹[e.g. 2650]
Unrealized P&L:  [e.g. +10.4%]
Thesis:          [Why did you buy? One sentence — e.g. "Energy-to-telecom transformation; Jio + retail flywheel undervalued vs sum-of-parts"]
Exit condition:  [What would make you sell? e.g. "Jio ARPU stagnates below ₹160 for 2 consecutive quarters"]

[HOLDING 2]
Ticker:          [e.g. INFY.NS]
Entry price:     ₹[X]
Entry date:      [YYYY-MM-DD]
Current price:   ₹[X]
Unrealized P&L:  [+/-X%]
Thesis:          [one sentence]
Exit condition:  [specific trigger]

[Add more holdings in the same format]

════════════════════════════════════════
CURRENT MARKET DATA  (as of [DATE])
════════════════════════════════════════

PRICE & VOLUME
[TICKER 1]: ₹[price], [+/-X%] today, Volume [X], Delivery [X]%, FII flow [+/-₹X Cr]
[TICKER 2]: ₹[price], [+/-X%] today, Volume [X], Delivery [X]%, FII flow [+/-₹X Cr]

TECHNICAL INDICATORS (from TradingView or similar)
[TICKER 1]:
  RSI:         [value]
  MACD:        [MACD line value] / Signal [signal line value] / Histogram [value]
  52w High:    ₹[X]  |  52w Low: ₹[X]
  Bollinger:   Upper ₹[X]  |  Middle ₹[X]  |  Lower ₹[X]
[TICKER 2]:
  RSI:         [value]
  MACD:        [X] / Signal [X] / Histogram [X]
  52w High:    ₹[X]  |  52w Low: ₹[X]
  Bollinger:   Upper ₹[X]  |  Middle ₹[X]  |  Lower ₹[X]

MACRO DATA
Brent Crude:    $[X]
Gold:           $[X]
USD/INR:        [X]
US 10Y Yield:   [X]%

════════════════════════════════════════
NEWS THIS WEEK
════════════════════════════════════════

INDIA NEWS:
1. [Headline] — [Source] — [One-line what it means for markets]
2. [Headline] — [Source] — [One-line what it means for markets]
3. [Headline] — [Source] — [One-line what it means for markets]
4. [Headline] — [Source] — [One-line what it means for markets]
5. [Headline] — [Source] — [One-line what it means for markets]

GLOBAL NEWS:
1. [Headline] — [Source] — [One-line what it might mean for India]
2. [Headline] — [Source] — [One-line what it might mean for India]
3. [Headline] — [Source] — [One-line what it might mean for India]

════════════════════════════════════════

Acknowledge all of the above and confirm you are ready for the analysis.
State the tickers in my portfolio so I know you've read them correctly.
Do not begin analyzing yet.
```

---

---

# PROMPT B — Signal Analysis (Layer 1 — Five Domains)

> **COPY AND PASTE THIS ENTIRE BLOCK AS-IS. No edits needed.**

```
Now perform a detailed signal analysis across five domains, using the portfolio
and data I provided above. Follow the chain-of-thought exactly for each domain.

══════════════════════════════════════════════════════════
DOMAIN 1 — INDIA BUSINESS SIGNALS
══════════════════════════════════════════════════════════

Scope: India-domestic business signals only.
Portfolio anchor rule: Only signals that directly affect a held ticker matter.
A macro trend that touches no held position is NOISE — discard it.

Chain-of-thought:
Step 1 — RBI/Policy: What is the policy environment signaling from the India news?
         Any RBI rate decisions, SEBI notifications, NSE/BSE corporate actions?
Step 2 — FII/DII flows: For each held ticker, what does the flow direction say?
         Net buying = accumulation. Net selling = distribution. Mixed = divergence.
Step 3 — Earnings & thesis impact: For each news item ask:
         "Does this change the EARNINGS or VALUATION thesis for any specific holding?"
         Name the holding and the exact mechanism. If it doesn't affect a held
         ticker, discard it and say why.
Step 4 — Uncertainty: Rate each signal — High (outcome unclear), Medium (directional
         but timing uncertain), Low (high conviction).

Output format:
- Reasoning chain: 4 steps as above
- Up to 5 signals, each with:
    Data point | Directional implication (Bullish/Bearish/Neutral) |
    India equity impact | Affected holding(s) | Uncertainty
- Overall: Dominant direction + Confidence

══════════════════════════════════════════════════════════
DOMAIN 2 — GEOPOLITICAL SIGNALS
══════════════════════════════════════════════════════════

Scope: Global events and their specific transmission into Indian markets.
Do NOT analyze domestic India news here — that was Domain 1.

Before analyzing ANY global event, apply this India Relevance Filter:
Does it affect India through one of these four channels?
  (a) Rupee channel:      US rates / dollar index → rupee → FII equity flows
  (b) Trade channel:      Tariffs / trade wars → India export sectors (IT, pharma, auto)
  (c) Oil channel:        Supply disruption → crude price → India CAD, inflation, RBI
  (d) EM sentiment:       Global risk-off → EM outflows → India liquidity, valuations
If NO clear channel exists → DISCARD. State why.
If YES → state the exact transmission chain explicitly.

Chain-of-thought:
Step 1 — Filter: Apply India relevance filter to each global headline.
         List every event as KEPT or DISCARDED with the reason.
Step 2 — Transmission chains: For each KEPT event, trace the exact chain:
         e.g. "Fed hold → Dollar index up → Rupee weakens → FII outflow risk → India equity discount"
Step 3 — Horizon: Tag each signal near-term (1-4 weeks) or structural (6-18 months).
         Do not blend them.
Step 4 — Direction and confidence.

Output format:
- India Relevance Filter log (every event: kept/discarded + reason)
- Up to 5 signals, each with:
    Global event | Transmission chain | Directional implication |
    Horizon | Uncertainty | Affected India sectors
- Overall: Dominant direction + Confidence

══════════════════════════════════════════════════════════
DOMAIN 3 — COMMODITY SIGNALS
══════════════════════════════════════════════════════════

Scope: Commodity prices translated into India-specific implications.
RULE: "Brent at $X" is NOT a signal. The signal is:
"Brent at $X implies Y% CAD widening → constrains RBI rate cuts → compresses equity multiples."
Every observation must end with a specific India equity impact.

Translation guide:
- Brent Crude (India imports ~80% of oil):
    >$95: CAD worsens → Rupee pressure → Inflation → RBI cannot cut → BEARISH
    $70-$95: Manageable range → NEUTRAL
    <$70: CAD improves → Inflation eases → RBI room to cut → BULLISH
- Gold:
    Rising WITH rising oil → FLIGHT-TO-SAFETY (flag this explicitly — not just inflation)
    Rising WITH falling oil → Global deflation fears → BEARISH
    Rising alone → Mild inflation hedge, uncertainty premium
- USD Index rising: Rupee pressure → FII outflows from India → BEARISH for equities

CRITICAL: If Gold AND Crude are BOTH rising, you must flag FLIGHT-TO-SAFETY explicitly.
This is different from pure inflation — it means markets are paying for safety.

Chain-of-thought:
Step 1 — Current levels vs historical bands for Brent, Gold, USD/INR, US 10Y.
Step 2 — India CAD/inflation/RBI translation for each commodity.
Step 3 — Supply-side check: is there a news-driven reason for current levels?
Step 4 — Gold + Oil co-movement check. If both rising → flag FLIGHT-TO-SAFETY.

Output format:
- Per-commodity analysis: price → level assessment → India impact → directional implication
- Flight-to-safety flag: YES / NO + explanation if YES
- Up to 4 signals with: Commodity | Data point | India impact | Directional implication | Uncertainty
- Overall: Dominant direction + Confidence

══════════════════════════════════════════════════════════
DOMAIN 4 — SECTOR SIGNALS
══════════════════════════════════════════════════════════

Scope: Sector-level story for the sectors IN my portfolio only.
Do not waste analysis on sectors with no held positions.

Sector identification:
- Tech:     INFY, TCS, Wipro, HCL Tech, Tech Mahindra
- Energy:   RELIANCE, ONGC, IOC, BPCL
- Banking:  HDFC Bank, ICICI Bank, SBI, Kotak
- FMCG:    Nestle, ITC, HUL, Dabur
- Pharma:   Sun Pharma, Dr Reddy's, Cipla
- Auto:     Maruti, Tata Motors, M&M, Bajaj Auto
- Metals:   Tata Steel, JSW, Hindalco

Chain-of-thought:
Step 1 — Identify which sectors I own. Explicitly skip everything else.
Step 2 — For each held sector: what do the India news items say about earnings,
         management commentary, order books, capex guidance?
Step 3 — Volume check: Is a sector rally or fall supported by volume conviction?
         A sector move on DECLINING volume is a WARNING — flag it explicitly.
Step 4 — SECULAR assessment (not daily noise): is the sector story getting
         BETTER, WORSE, or UNCHANGED vs 3 months ago? State the specific evidence.

Output format:
- Sectors identified (only the ones I hold)
- Per-sector signal: Sector | Key finding | Thesis status (Intact/Weakening/Broken) |
  Volume support (Yes/No/Warning) | Directional implication | Uncertainty | Affected holdings
- Overall: Dominant direction + Confidence

══════════════════════════════════════════════════════════
DOMAIN 5 — TECHNICAL / QUANT SIGNALS
══════════════════════════════════════════════════════════

Scope: Technical analysis for my held tickers only, using the indicators I provided.
Your only question: "What is the technical posture of what I own?"
NO-INTERPRETATION RULE: Report what price is doing, not why. Do not mix
fundamentals here — that was Domains 1-4.

Chain-of-thought:
Step 1 — RSI: State value and zone:
         >70 = Overbought | 50-70 = Bullish zone | 30-50 = Bearish zone | <30 = Oversold
Step 2 — MACD: Is MACD line above or below signal line?
         If histogram is flipping sign (pos→neg or neg→pos), note "FRESH CROSSOVER" — stronger signal.
Step 3 — 52-week range percentile:
         Formula: (current price − 52w low) ÷ (52w high − 52w low) × 100
         >75th percentile = near highs | 25th–75th = mid-range | <25th = near lows
Step 4 — Bollinger Band position: above upper band / within bands (near middle) / below lower band
Step 5 — Volume/delivery note:
         Delivery% >60% with a price move = conviction buying/selling
         Low delivery% with a price move = weak signal, likely speculative

Output format:
- Per-holding technical reading:
    Ticker | Current price | RSI (value + zone) | MACD signal + fresh crossover? |
    52w percentile + position | BB position | Delivery% note | Technical posture (Bullish/Bearish/Neutral) |
    One-line posture summary
- Overall: Dominant direction + Confidence

══════════════════════════════════════════════════════════

Complete all 5 domains now in order. Label each section clearly.
Do not begin the synthesis yet — wait for my next prompt.
```

---

---

# PROMPT C — Lead Synthesis (Layer 2 — Three Scorecards)

> **COPY AND PASTE THIS ENTIRE BLOCK AS-IS. No edits needed.**

```
Now synthesise the five signal domains above into three lead scorecards.
Use only what you found in the analysis above — do not bring in new information.

══════════════════════════════════════════════════════════
SCORECARD 1 — MACRO LEAD
(synthesises: Geopolitical + Commodity signals)
══════════════════════════════════════════════════════════

Your job: Combine the global macro picture into a single actionable scorecard
for Indian equities overall.

DISSENT FIRST — before stating your thesis, look for the one signal that
contradicts your overall view. Write the dissent note before anything else.
The anomaly is often where alpha hides.
  - What is the anomaly or contradicting signal?
  - How significant is it? (High / Medium / Low)
  - What would it mean if it turns out to be correct?

Then synthesise:
  - What does the combined macro environment (global + commodity) mean for India
    equity direction and confidence?
  - What is the primary driver?
  - Is there an escalation? (Something requiring attention NOW, not next week)
  - Horizon: near-term (1-4 weeks) or structural (6-18 months)?

Output:
  Dissent note: [anomaly | significance | implication if correct]
  Macro thesis: [one clear sentence]
  Direction: bullish / bearish / neutral
  Confidence: high / medium / low
  Horizon: near-term / structural
  Escalation flag: YES / NO + reason if yes
  Reasoning chain: [3-4 steps showing how you got there]

══════════════════════════════════════════════════════════
SCORECARD 2 — MICRO LEAD
(synthesises: India Business + Sector signals)
══════════════════════════════════════════════════════════

Your job: Synthesise the India domestic picture for my specific portfolio.

Thesis integrity check — for EACH holding:
  Cross-reference the signals from Domains 1 and 4 against the original thesis
  I stated in my portfolio. Ask: "Is this thesis getting stronger, weaker, or
  is it unchanged?" Be specific about WHAT has changed, not generic.

Escalation check:
  Is any holding's thesis at serious risk of being invalidated by the current signals?
  If yes → escalation flag = true. Name the holding and the specific threat.

Then synthesise the domestic India picture overall.

Output:
  Per-holding thesis status: [Ticker | Intact / Weakening / Broken | one-line reason]
  Escalation flag: YES / NO + holding name + specific threat if yes
  Micro direction: bullish / bearish / neutral
  Confidence: high / medium / low
  Reasoning chain: [3-4 steps]

══════════════════════════════════════════════════════════
SCORECARD 3 — QUANT LEAD
(synthesises: Technical signals + both scorecards above)
══════════════════════════════════════════════════════════

Your job: Cross-reference technical posture against the macro and micro views.
Identify where they AGREE and where they DIVERGE.

Key divergence rules to check for each holding:
  - Price RISING but macro/micro BEARISH → possible distribution (smart money selling into strength). Flag explicitly.
  - Price FALLING but macro/micro BULLISH → possible accumulation (smart money buying weakness). Flag explicitly.
  - All three ALIGNED → higher conviction. Note this.
  - Price action CONTRADICTING both macro and micro → strong warning. Note this.

Output:
  Per-holding alignment: [Ticker | Aligned / Diverging / Conflicted | one-line note]
  Key divergences: [list any — these are the most important signals]
  Calibration note: Does the technical picture ADD or SUBTRACT conviction from the macro+micro view?
  Overall: Does quant CONFIRM / QUESTION / CONTRADICT the macro+micro scorecard?

══════════════════════════════════════════════════════════

Complete all 3 scorecards now. Label each clearly.
Do not make final decisions yet — wait for my next prompt.
```

---

---

# PROMPT D — Final Decisions (Layer 3 — Chief Orchestrator)

> **COPY AND PASTE THIS ENTIRE BLOCK AS-IS. No edits needed.**

```
You are now acting as the Chief Orchestrator. Using everything above —
the 5 signal domains and 3 lead scorecards — make a final decision for each holding.

Apply this exact 5-step process for EACH holding separately:

STEP 1 — ANTI-RECENCY CHECK
Before anything else: is the most recent news (last 1-2 weeks) being
over-weighted compared to the 12-month trend?
State explicitly: what is the 12-month context for this holding and its sector?
This step exists to prevent reacting to noise.

STEP 2 — THESIS INTEGRITY
Cross-reference the current signals against my ORIGINAL thesis (as I stated it).
Is the thesis still intact? If it's weakening — what specifically changed?
What would need to happen to call the thesis definitively BROKEN?

STEP 3 — BLANK SLATE TEST
Imagine you have no position and ₹X to deploy today.
Ask: "Given this thesis, these signals, and the current price — would I BUY
this stock today if I owned none of it?"
Answer YES or NO.
  - YES → PASS (thesis holds even without the sunk cost of existing position)
  - NO → FAIL (you would not enter this at current price/thesis/signals)
A FAIL does not automatically mean exit — but you MUST name the sunk cost
bias explicitly: "I am holding because I am down X% / up X%, not because
the thesis supports staying."

STEP 4 — CONFLICT RESOLUTION
If macro, micro, and quant signals point in different directions:
  - Which signal is MOST relevant to this specific holding and why?
  - Do NOT average the signals. Pick the dominant one and justify the choice.
  - Example: "For an IT stock, the sector signal and US macro dominate.
    The commodity signal is less relevant here."

STEP 5 — FINAL DECISION
Based on steps 1-4, assign ONE of:

  HOLD — Thesis intact, blank slate passes, no immediate threat.
          State: what you are watching for that would change this.

  WATCH — Thesis weakening OR blank slate borderline OR signals conflicted.
           State: the SPECIFIC trigger that would move this to EXIT.
           Be concrete: not "if things deteriorate" but "if RSI drops below 30
           AND sector thesis breaks, then exit."

  EXIT_CONDITION_APPROACHING — One or more of:
           (a) Original exit condition has been met or is being met
           (b) Thesis is broken (not just weakening)
           (c) Blank slate FAIL + macro/micro both bearish

══════════════════════════════════════════════════════════

Format your output as follows for each holding:

── [TICKER] ──────────────────────────────────
Flag:                 HOLD / WATCH / EXIT_CONDITION_APPROACHING
Thesis status:        Intact / Weakening / Broken
Technical alignment:  Aligned / Diverging / Conflicted
Blank slate test:     PASS / FAIL
  (if FAIL): [name the sunk cost bias explicitly — "I am holding because..."]
Decision reason:      [ONE sentence — the single most important driver]

Reasoning chain:
  Step 1 — Anti-recency: [12-month context vs recent noise]
  Step 2 — Thesis integrity: [what changed, what would break it]
  Step 3 — Blank slate: [YES/NO + reasoning]
  Step 4 — Conflict resolution: [which signal dominates and why]
  Step 5 — Decision: [final call + what to watch]

══════════════════════════════════════════════════════════

After all holdings, provide a PORTFOLIO SUMMARY:

Overall portfolio posture:    [one sentence]
Highest conviction action:    [the most urgent thing, if any]
Watch list this week:         [2-3 specific, concrete triggers to monitor]
  - e.g. "Watch RBI minutes on [date] for tone change on rate cuts"
  - e.g. "Watch INFY.NS — if it closes below ₹1200 on high delivery, thesis breaks"
  - e.g. "Watch Brent Crude — if it crosses $90, re-evaluate RELIANCE thesis"

══════════════════════════════════════════════════════════
```

---

---

## TIPS FOR BEST RESULTS

**For news quality:**
Use ET Markets, Moneycontrol, and NSE website for India news.
Use Reuters and Bloomberg for global news. The better the news you provide in Prompt A, the better the analysis.

**For technical data:**
TradingView is the easiest source. Open your ticker, set the chart to Daily timeframe,
add RSI (14), MACD (12,26,9), and Bollinger Bands (20,2) from the indicators panel.
Read the values directly from the panel.

**Refresh cadence:**
- Run the full chain every Sunday morning before markets open
- Run Prompts B → D only (skip A) if you already have a recent portfolio setup
  and only the news has changed — tell Claude "My portfolio is the same as before.
  Here is the new data for this week:" then paste just the updated market data and news

**If a thesis breaks mid-week:**
Start a new chat. Paste Prompt A with updated portfolio notes and the specific
news event that may have broken the thesis. Then run Prompts B → D.

**Saving your output:**
Copy the final output from Prompt D and save it in a notes app or a file
with the date. This becomes your decision log — useful for tracking whether
the system's recommendations turn out to be right or wrong over time.
