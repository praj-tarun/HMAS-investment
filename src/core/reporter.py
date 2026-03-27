"""
reporter.py — Generates Human-Readable Executive Briefs for HMAS analysis.

Portfolio mode: 4-section brief per holding (Business News, Macro, Quant, Drishti conclusion).
General mode:  4-section market intelligence memo (Policy, Macro, Sectors, Drishti call).

Both formats:
  - Markdown tables for data
  - Bullet points for reasoning
  - Professional hedge fund memo tone
  - No internal system jargon ("anti-recency", "Step N —", "Test reason")
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional


# ── Plain-English label maps ──────────────────────────────────────────────────

_FLAG_LABELS = {
    "HOLD": "Hold — Thesis Intact, No Action Required",
    "WATCH": "Watch — Thesis Weakening, Prepare Exit Criteria",
    "EXIT_CONDITION_APPROACHING": "Exit / Rotate — Exit Condition Approaching or Triggered",
}
_FLAG_EMOJI = {"HOLD": "✅", "WATCH": "⚠️", "EXIT_CONDITION_APPROACHING": "🔴"}

_THESIS_LABELS = {
    "Intact": "Intact — original buy rationale remains valid",
    "Weakening": "Weakening — key assumptions under pressure",
    "Broken": "Broken — original rationale no longer holds",
}

_DIRECTION_ARROW = {"bullish": "↑ Bullish", "bearish": "↓ Bearish", "neutral": "→ Neutral"}
_DIRECTION_CONF = {"high": "High", "medium": "Medium", "low": "Low"}

_ALIGN_LABEL = {
    "Aligned": "Aligned — price confirms fundamentals",
    "Diverging": "Diverging — price moving against fundamentals",
    "Conflicted": "Conflicted — technicals directly contradict macro view",
    "Neutral": "Neutral — technicals inconclusive",
}


# ── Public entry point ────────────────────────────────────────────────────────

def save_report(
    result: Dict[str, Any],
    mode: str,
    output_dir: str = "reports",
) -> Path:
    """
    Save a full HMAS result dict to a markdown executive brief.

    Args:
        result:     The dict returned by HMASWorkflow.run_full_cycle()
        mode:       "portfolio" or "general"
        output_dir: Directory to save reports in (created if missing)

    Returns:
        Path to the saved file.
    """
    reports_dir = Path(output_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    ts = result.get("timestamp", datetime.now().isoformat())
    date_str = ts[:10]
    time_str = ts[11:19].replace(":", "-")

    base_name = f"{date_str}_{mode}"
    file_path = reports_dir / f"{base_name}.md"
    if file_path.exists():
        file_path = reports_dir / f"{base_name}_{time_str}.md"

    if mode == "general":
        content = _build_general_brief(result)
    elif mode == "scout_v2":
        content = _build_scout_v2_brief(result)
    elif mode == "portfolio_v2":
        content = _build_portfolio_v2_brief(result)
    else:
        content = _build_portfolio_brief(result)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


# ── Portfolio Report ──────────────────────────────────────────────────────────

def _build_portfolio_brief(result: Dict[str, Any]) -> str:
    ts = result.get("timestamp", "")[:19].replace("T", " ")
    briefs = result.get("briefs", [])
    trail = result.get("signal_trail", {}) or {}

    L = []
    L += [
        f"# HMAS Executive Brief — Portfolio Review",
        f"*{ts} | {len(briefs)} Holding(s) Analysed*",
        "",
        "---",
        "",
    ]

    # Market context banner (replaces "anti-recency check" jargon)
    arc = result.get("anti_recency_check", "")
    if arc:
        L += [
            "> **12-Month Market Context:** " + arc,
            "",
        ]

    if not briefs:
        L += ["*No holdings to analyse. Add positions with `python run.py add TICKER.NS`.*", ""]
        L += _footer()
        return "\n".join(L)

    for b in briefs:
        if not isinstance(b, dict):
            continue
        ticker = b.get("ticker", "UNKNOWN")
        flag = b.get("flag", "HOLD")
        pnl = _extract_pnl_from_notes(b.get("blank_slate_notes", ""), b)

        L += [f"---", ""]
        L += [f"## {ticker}", ""]
        L += _verdict_banner(b)
        L += [""]
        L += _section1_india_news(trail, ticker, pnl)
        L += _section2_macro(trail)
        L += _section3_quant(trail, ticker)
        L += _section4_drishti_portfolio(b, trail)

    L += ["---", ""]
    L += _footer()
    return "\n".join(L)


def _verdict_banner(b: dict) -> List[str]:
    flag = b.get("flag", "HOLD")
    bst = b.get("blank_slate_test", "PASS")
    thesis = b.get("thesis_status", "Intact")
    tech = b.get("technical_alignment", "Neutral")

    icon = _FLAG_EMOJI.get(flag, "")
    label = _FLAG_LABELS.get(flag, flag)
    bst_label = "Yes — thesis stands on current merits" if bst == "PASS" else "No — sunk cost risk (see Section 4)"

    return [
        f"| | |",
        f"|---|---|",
        f"| **Verdict** | {icon} **{label}** |",
        f"| **Thesis** | {_THESIS_LABELS.get(thesis, thesis)} |",
        f"| **Technicals** | {_ALIGN_LABEL.get(tech, tech)} |",
        f"| **Fresh Buyer Would Buy?** | {bst_label} |",
    ]


# ── Section 1: Business & India News ─────────────────────────────────────────

def _section1_india_news(trail: dict, ticker: str, pnl: float) -> List[str]:
    L = [
        "### Section 1 — Business & India News",
        "*India Business Agent + Sector Agent — domestic policy, earnings, flows*",
        "",
    ]

    pnl_str = f"{pnl:+.1f}%" if pnl else "your position"
    recovery_phrase = f"recovery from {pnl_str}" if pnl else "recovery"

    # Collect signals from india_business and sector, filtered to this ticker
    india_biz = trail.get("india_business") or {}
    sector = trail.get("sector") or {}

    points = []

    for sig in (india_biz.get("signals") or []):
        dp = sig.get("data_point", "")
        impact = sig.get("india_impact", "")
        holders = sig.get("affected_holdings", [])
        # Include if relevant to this ticker or if general market signal
        if not dp:
            continue
        if holders and ticker not in holders and "general market" not in str(holders).lower():
            continue
        direction = sig.get("directional_implication", "Neutral")
        unc = sig.get("uncertainty", "")
        points.append((dp, impact, direction, unc, "India Business"))

    for sig in (sector.get("signals") or []):
        dp = sig.get("data_point", "")
        impact = sig.get("india_impact", "")
        holders = sig.get("affected_holdings", [])
        if not dp:
            continue
        if holders and ticker not in holders:
            continue
        direction = sig.get("directional_implication", "Neutral")
        unc = sig.get("uncertainty", "")
        thesis_s = sig.get("thesis_status", "")
        label = f"{dp}" + (f" — thesis {thesis_s}" if thesis_s else "")
        points.append((label, impact, direction, unc, "Sector"))

    if not points:
        # Fall back to micro_lead reasoning chain
        micro = trail.get("micro_lead") or {}
        chain = micro.get("reasoning_chain") or []
        if chain:
            L += ["*No ticker-specific signals available. Summary from Micro Lead synthesis:*", ""]
            for step in chain[:3]:
                cleaned = _clean_step(step)
                if cleaned:
                    L.append(f"- {cleaned}")
            L.append("")
        else:
            L += ["*No India business signals available for this ticker.*", ""]
        return L

    for dp, impact, direction, unc, source in points[:5]:
        arrow = "↑" if "bullish" in direction.lower() else ("↓" if "bearish" in direction.lower() else "→")
        L.append(f"- **{dp}** {arrow}")
        if impact:
            L.append(f"  *Significance for {recovery_phrase}: {impact}*")
        L.append("")

    # RBI / policy note from reasoning chain if available
    micro = trail.get("micro_lead") or {}
    micro_thesis = micro.get("thesis", "")
    if micro_thesis:
        L += [
            f"> **Micro Lead Synthesis ({_direction_label(micro.get('direction',''))}):** {micro_thesis}",
            "",
        ]

    return L


# ── Section 2: Macro & Geopolitical Context ───────────────────────────────────

def _section2_macro(trail: dict) -> List[str]:
    L = [
        "### Section 2 — Macro & Geopolitical Context",
        "*Commodity Agent + Geopolitical Agent + Macro Lead — global trends and their India impact*",
        "",
    ]

    commodity = trail.get("commodity") or {}
    geo = trail.get("geopolitical") or {}
    macro_lead = trail.get("macro_lead") or {}

    # Build commodity/macro data table
    table_rows = []
    for sig in (commodity.get("signals") or []):
        dp = sig.get("data_point", "")
        impact = sig.get("india_impact", "")
        direction = sig.get("directional_implication", "Neutral")
        commodity_name = sig.get("commodity", "")
        if not dp:
            continue
        arrow = "↑" if "bullish" in direction.lower() else ("↓" if "bearish" in direction.lower() else "→")
        label = commodity_name if commodity_name else dp[:40]
        table_rows.append((label, dp[:50], f"{arrow} {direction}", impact[:70] if impact else "—"))

    # Add macro stance row
    if macro_lead:
        direction = _direction_label(macro_lead.get("direction", ""))
        conf = macro_lead.get("confidence", "")
        horizon = macro_lead.get("horizon", "")
        table_rows.append(("India Equity Macro", f"{conf.capitalize()} confidence, {horizon}", direction, macro_lead.get("thesis", "")[:70]))

    if table_rows:
        L += [
            "| Indicator | Level / Status | Direction | India Implication |",
            "|---|---|---|---|",
        ]
        for row in table_rows:
            L.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
        L.append("")

    # Geopolitical signals as bullets (reasoning, not data)
    geo_signals = geo.get("signals") or []
    if geo_signals:
        L.append("**Geopolitical transmission chains this week:**")
        L.append("")
        for sig in geo_signals[:4]:
            dp = sig.get("data_point", "")
            chain = sig.get("india_transmission_mechanism", "")
            horizon = sig.get("horizon", "")
            if not dp:
                continue
            horizon_tag = f" ({horizon})" if horizon else ""
            L.append(f"- **{dp}**{horizon_tag}")
            if chain:
                L.append(f"  *India impact: {chain}*")
            L.append("")

    # Macro Lead dissent / key risk
    da = macro_lead.get("dissent_appendix") or {}
    dissent_summary = da.get("dissent_summary", "")
    significance = da.get("anomaly_significance", "")
    if dissent_summary and significance and significance.lower() not in ("none", "low"):
        L += [
            f"> **Contra-Signal ({significance} significance):** {dissent_summary}",
            "",
        ]

    # Margin of Safety note from macro reasoning
    macro_chain = macro_lead.get("reasoning_chain") or []
    mos_steps = [_clean_step(s) for s in macro_chain if s and "india" in s.lower()][:2]
    if mos_steps:
        L.append("**Significance — Margin of Safety for your stocks:**")
        L.append("")
        for s in mos_steps:
            if s:
                L.append(f"- {s}")
        L.append("")

    return L


# ── Section 3: Technical Patterns & Quant Signals ────────────────────────────

def _section3_quant(trail: dict, ticker: str) -> List[str]:
    L = [
        "### Section 3 — Technical Patterns & Quant Signals",
        f"*Quant Agent + Quant Lead — price action for {ticker}*",
        "",
    ]

    quant = trail.get("quant") or {}
    quant_lead = trail.get("quant_lead") or {}

    # Find this ticker's technical data from quant signals
    ticker_tech = None
    for sig in (quant.get("signals") or []):
        if sig.get("ticker") == ticker:
            ticker_tech = sig
            break

    if ticker_tech:
        rsi = ticker_tech.get("rsi")
        rsi_zone = ticker_tech.get("rsi_zone", "")
        macd_sig = ticker_tech.get("macd_signal", "")
        fresh_cross = ticker_tech.get("fresh_crossover", False)
        pct_52w = ticker_tech.get("price_52w_percentile")
        pos_52w = ticker_tech.get("price_52w_position", "")
        bb_pos = ticker_tech.get("bb_position", "")
        posture = ticker_tech.get("posture_detail", ticker_tech.get("directional_implication", ""))

        # RSI signal
        rsi_signal = "Oversold — potential capitulation" if rsi and rsi < 30 else (
            "Bearish zone — no buying signal" if rsi and rsi < 50 else (
            "Bullish momentum" if rsi and rsi < 70 else "Overbought — distribution risk"))

        # MACD label
        macd_label = macd_sig
        if fresh_cross:
            macd_label += " [Fresh crossover — stronger signal]"

        # Support / Resistance from bb_position
        bb_note = {
            "Above upper": "Trading above upper band — stretched, distribution risk",
            "Within bands": "Within Bollinger Bands — no extreme reading",
            "Below lower": "Below lower band — oversold extreme",
        }.get(bb_pos, bb_pos)

        L += [
            "| Indicator | Reading | Signal |",
            "|---|---|---|",
            f"| RSI (14-period) | {f'{rsi:.1f}' if rsi else 'N/A'} — {rsi_zone} | {rsi_signal} |",
            f"| MACD | {macd_label} | {'Bearish' if 'bear' in macd_label.lower() else 'Bullish'} momentum |",
            f"| Bollinger Bands | {bb_pos} | {bb_note} |",
            f"| 52-Week Range | {_ordinal(pct_52w)} — {pos_52w} | {'Near historical lows' if pct_52w and pct_52w < 30 else ('Near historical highs' if pct_52w and pct_52w > 70 else 'Mid-range')} |",
            "",
        ]

        # Volume / Smart Money bullet
        volume_note = ticker_tech.get("volume_note", "")
        if volume_note:
            L.append(f"- **Volume / Delivery:** {volume_note}")
            L.append("")

        # Overall posture
        if posture:
            L.append(f"- **Technical Posture:** {posture}")
            L.append("")

    else:
        L += ["*No technical data available for this ticker.*", ""]

    # Smart Money signal from Quant Lead alignment
    alignment_scores = quant_lead.get("alignment_scores") or {}
    ticker_alignment = alignment_scores.get(ticker) or {}
    alignment = ticker_alignment.get("alignment", "")
    divergence = ticker_alignment.get("divergence_note", "")
    tech_summary = ticker_alignment.get("technical_summary", "")

    if alignment:
        smart_money = {
            "Aligned": "Technicals and fundamentals agree — no divergence detected.",
            "Diverging": "Price moving against the fundamental view — possible leading indicator of deterioration.",
            "Conflicted": "Strong technical extreme contradicts the macro/micro call — watch carefully.",
            "Neutral": "Technical picture is flat — no actionable signal from price alone.",
        }.get(alignment, alignment)

        L.append(f"- **Smart Money Signal ({alignment}):** {smart_money}")
        if divergence:
            L.append(f"  *Key divergence: {divergence}*")
        L.append("")

    key_divs = quant_lead.get("key_divergences") or []
    if key_divs:
        L.append("**Flagged Divergences:**")
        L.append("")
        for d in key_divs:
            L.append(f"- {d}")
        L.append("")

    return L


# ── Section 4: The 'Drishti' Conclusion (Portfolio) ──────────────────────────

def _section4_drishti_portfolio(b: dict, trail: dict) -> List[str]:
    flag = b.get("flag", "HOLD")
    bst = b.get("blank_slate_test", "PASS")
    reason = b.get("reason", "")
    thesis_note = b.get("thesis_validation_note", "")
    bst_notes = b.get("blank_slate_notes", "")
    thesis_status = b.get("thesis_status", "Intact")
    chain = b.get("reasoning_chain") or []

    icon = _FLAG_EMOJI.get(flag, "")
    label = _FLAG_LABELS.get(flag, flag)

    L = [
        "### Section 4 — The 'Drishti' Conclusion",
        "*Chief Orchestrator — final verdict integrating all three layers*",
        "",
        f"**Decision: {icon} {label}**",
        "",
    ]

    # Primary driver (the reason without internal jargon)
    if reason:
        L += [f"**Primary Driver:** {reason}", ""]

    # Why Now — cross-layer conflict (extract from reasoning chain)
    conflict_steps = _extract_conflict_from_chain(chain, trail)
    if conflict_steps:
        L += ["**Why Now — Layer Conflict:**", ""]
        for step in conflict_steps:
            L.append(f"- {step}")
        L.append("")

    # Thesis integrity
    thesis_label = _THESIS_LABELS.get(thesis_status, thesis_status)
    L += [f"**Thesis Integrity:** {thesis_label}"]
    if thesis_note:
        L += [f"  {thesis_note}"]
    L.append("")

    # Sunk cost check — clean language
    if bst == "FAIL" and bst_notes:
        # Present bst_notes as-is (LLM already wrote it in the required language)
        L += [
            "> **Sunk Cost Check (Fresh Buyer Test — FAIL):**",
            f"> {bst_notes}",
            "",
        ]
    elif bst == "PASS":
        L += [
            "> **Sunk Cost Check (Fresh Buyer Test — PASS):** "
            "Current data supports initiating a new position. Hold is not sunk-cost-driven.",
            "",
        ]

    return L


# ── General Market Report ─────────────────────────────────────────────────────

def _build_general_brief(result: Dict[str, Any]) -> str:
    ts = result.get("timestamp", "")[:19].replace("T", " ")
    trail = result.get("signal_trail", {}) or {}
    gmb_raw = result.get("general_market_brief")
    arc = result.get("anti_recency_check", "")

    # Normalise: GeneralMarketBrief can be a dataclass or dict
    gmb = _to_dict(gmb_raw) if gmb_raw else {}

    macro_dir = _direction_label(gmb.get("macro_direction", "neutral"))
    macro_conf = _DIRECTION_CONF.get(gmb.get("macro_confidence", "medium"), "Medium")
    macro_hor = gmb.get("macro_horizon", "near-term")

    L = [
        "# HMAS Market Intelligence Brief — India Equities",
        f"*{ts} | General Market Mode*",
        "",
        "---",
        "",
        f"**Market Stance: {macro_dir}** | Confidence: {macro_conf} | Horizon: {macro_hor}",
        "",
    ]

    if arc:
        L += [f"> **Market Context:** {arc}", ""]

    L += _general_section1_india(trail, gmb)
    L += _general_section2_macro(trail, gmb)
    L += _general_section3_sectors(trail, gmb)
    L += _general_section4_drishti(gmb, trail)

    L += ["---", ""]
    L += _footer()
    return "\n".join(L)


def _general_section1_india(trail: dict, gmb: dict) -> List[str]:
    L = [
        "---",
        "",
        "### Section 1 — India Business & Policy Environment",
        "*India Business Agent + Sector Agent — RBI, FII flows, earnings, domestic activity*",
        "",
    ]

    india_biz = trail.get("india_business") or {}
    sector = trail.get("sector") or {}

    points = []
    for sig in (india_biz.get("signals") or []):
        dp = sig.get("data_point", "")
        impact = sig.get("india_impact", "")
        direction = sig.get("directional_implication", "Neutral")
        if dp:
            points.append((dp, impact, direction))

    for sig in (sector.get("signals") or []):
        dp = sig.get("data_point", "")
        impact = sig.get("india_impact", "")
        direction = sig.get("directional_implication", "Neutral")
        sector_name = sig.get("sector", "")
        if dp:
            label = f"[{sector_name}] {dp}" if sector_name else dp
            points.append((label, impact, direction))

    if points:
        for dp, impact, direction in points[:5]:
            arrow = "↑" if "bullish" in direction.lower() else ("↓" if "bearish" in direction.lower() else "→")
            L.append(f"- **{dp}** {arrow}")
            if impact:
                L.append(f"  *Significance: {impact}*")
            L.append("")
    else:
        micro = trail.get("micro_lead") or {}
        for step in (micro.get("reasoning_chain") or [])[:3]:
            cleaned = _clean_step(step)
            if cleaned:
                L.append(f"- {cleaned}")
        L.append("")

    micro_thesis = (trail.get("micro_lead") or {}).get("thesis", "")
    if micro_thesis:
        micro_dir = _direction_label((trail.get("micro_lead") or {}).get("direction", ""))
        L += [f"> **Domestic Outlook ({micro_dir}):** {micro_thesis}", ""]

    return L


def _general_section2_macro(trail: dict, gmb: dict) -> List[str]:
    L = [
        "---",
        "",
        "### Section 2 — Global Macro & Geopolitical Context",
        "*Commodity Agent + Geopolitical Agent + Macro Lead*",
        "",
    ]

    commodity = trail.get("commodity") or {}
    geo = trail.get("geopolitical") or {}
    macro_lead = trail.get("macro_lead") or {}

    # Commodity table
    table_rows = []
    for sig in (commodity.get("signals") or []):
        dp = sig.get("data_point", "")
        impact = sig.get("india_impact", "")
        direction = sig.get("directional_implication", "Neutral")
        name = sig.get("commodity", dp[:30])
        if dp:
            arrow = "↑" if "bullish" in direction.lower() else ("↓" if "bearish" in direction.lower() else "→")
            table_rows.append((name, dp[:50], f"{arrow} {direction}", impact[:70] if impact else "—"))

    # Add geo signals to table
    for sig in (geo.get("signals") or [])[:3]:
        dp = sig.get("data_point", "")
        impact = sig.get("india_transmission_mechanism", "")
        direction = sig.get("directional_implication", "Neutral")
        horizon = sig.get("horizon", "")
        if dp:
            arrow = "↑" if "bullish" in direction.lower() else ("↓" if "bearish" in direction.lower() else "→")
            label = f"{dp[:40]}" + (f" ({horizon})" if horizon else "")
            table_rows.append((label, "Global event", f"{arrow} {direction}", impact[:70] if impact else "—"))

    if table_rows:
        L += [
            "| Indicator / Event | Level / Status | Direction | India Impact |",
            "|---|---|---|---|",
        ]
        for row in table_rows:
            L.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
        L.append("")

    # Macro dissent
    da = macro_lead.get("dissent_appendix") or {}
    ds = da.get("dissent_summary", "")
    sig_lvl = da.get("anomaly_significance", "None")
    if ds and sig_lvl.lower() not in ("none", "low"):
        L += [f"> **Contra-Signal ({sig_lvl} significance):** {ds}", ""]

    # Macro thesis
    macro_thesis = macro_lead.get("thesis", "") or gmb.get("macro_thesis", "")
    if macro_thesis:
        macro_dir = _direction_label(macro_lead.get("direction", "") or gmb.get("macro_direction", ""))
        L += [f"> **Global Macro Call ({macro_dir}):** {macro_thesis}", ""]

    return L


def _general_section3_sectors(trail: dict, gmb: dict) -> List[str]:
    L = [
        "---",
        "",
        "### Section 3 — Sector Snapshot",
        "*Sector Agent — India sector-level developments*",
        "",
    ]

    sector = trail.get("sector") or {}
    sector_signals = sector.get("signals") or []
    gmb_sectors = gmb.get("sector_signals") or []

    # Use gmb sectors if available (richer from orchestrator), otherwise from trail
    display_sectors = gmb_sectors if gmb_sectors else [
        {
            "sector": s.get("sector", ""),
            "direction": s.get("directional_implication", "Neutral"),
            "key_signal": s.get("data_point", ""),
        }
        for s in sector_signals if s.get("sector")
    ]

    if display_sectors:
        L += [
            "| Sector | Direction | Key Development |",
            "|---|---|---|",
        ]
        for s in display_sectors[:6]:
            sector_name = s.get("sector", "")
            direction = s.get("direction", "Neutral")
            key_sig = s.get("key_signal", "")
            arrow = "↑" if "bullish" in direction.lower() else ("↓" if "bearish" in direction.lower() else "→")
            L.append(f"| {sector_name} | {arrow} {direction} | {key_sig[:80]} |")
        L.append("")
    else:
        L += ["*No sector-specific signals available.*", ""]

    # Commodity context
    brent = gmb.get("commodity_brent_impact", "")
    gold = gmb.get("commodity_gold_signal", "")
    if brent:
        L.append(f"- **Crude Oil:** {brent}")
    if gold:
        L.append(f"- **Gold:** {gold}")
    if brent or gold:
        L.append("")

    if gmb.get("flight_to_safety_active"):
        L += ["> **ALERT: Flight-to-Safety signal active** — Gold and Oil rising simultaneously signals risk-off. Review equity allocation.", ""]

    return L


def _general_section4_drishti(gmb: dict, trail: dict) -> List[str]:
    macro_dir = _direction_label(gmb.get("macro_direction", "neutral"))
    macro_conf = gmb.get("macro_confidence", "medium").capitalize()
    macro_hor = gmb.get("macro_horizon", "near-term")
    macro_thesis = gmb.get("macro_thesis", "")
    week_review = gmb.get("week_in_review", "")
    top_risks = gmb.get("top_risks") or []
    macro_dissent = gmb.get("macro_dissent", "")
    micro_dir = _direction_label(gmb.get("micro_direction", "neutral"))
    micro_thesis = gmb.get("micro_thesis", "")

    L = [
        "---",
        "",
        "### Section 4 — The 'Drishti' Market Call",
        "*Chief Orchestrator — synthesised view for an investor considering Indian equities*",
        "",
        f"**Market Environment: {macro_dir}** | Confidence: {macro_conf} | Horizon: {macro_hor}",
        "",
    ]

    if macro_thesis:
        L += [f"**What's Driving It:**", ""]
        L += [f"- {macro_thesis}", ""]

    if micro_thesis:
        L += [f"**Domestic Micro ({micro_dir}):** {micro_thesis}", ""]

    # Layer conflict (macro vs micro)
    macro_lead = trail.get("macro_lead") or {}
    micro_lead = trail.get("micro_lead") or {}
    m_dir = macro_lead.get("direction", "")
    mi_dir = micro_lead.get("direction", "")
    if m_dir and mi_dir and m_dir != mi_dir:
        L += [
            f"> **Layer Conflict:** Macro is {_direction_label(m_dir)} while domestic Micro is {_direction_label(mi_dir)}. "
            f"This divergence is a key risk to watch — a shift in either direction could resolve the tension quickly.",
            "",
        ]

    if week_review:
        L += ["**Week in Review:**", "", week_review, ""]

    if top_risks:
        L += ["**Top Risks to Watch:**", ""]
        for i, r in enumerate(top_risks[:5], 1):
            L.append(f"{i}. {r}")
        L.append("")

    if macro_dissent:
        L += [f"> **Contra-Signal / Dissent:** {macro_dissent}", ""]

    return L


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_conflict_from_chain(chain: list, trail: dict) -> List[str]:
    """
    Extract 1-2 meaningful conflict sentences from orchestrator reasoning chain.
    Strips Step N prefixes and returns the most substantive lines.
    """
    if not chain:
        # Fall back to macro/micro conflict
        macro = trail.get("macro_lead") or {}
        micro = trail.get("micro_lead") or {}
        conflicts = []
        m = macro.get("direction", "")
        mi = micro.get("direction", "")
        if m and mi and m != mi:
            conflicts.append(
                f"Macro environment is {_direction_label(m)} but domestic Micro signals are "
                f"{_direction_label(mi)} — layers disagree on the near-term direction."
            )
        da = macro.get("dissent_appendix") or {}
        ds = da.get("dissent_summary", "")
        if ds:
            conflicts.append(f"Key anomaly in macro picture: {ds}")
        return conflicts[:2]

    cleaned = []
    for step in chain:
        s = _clean_step(step)
        # Keep steps that describe a conflict, thesis issue, or blank slate finding
        if s and any(kw in s.lower() for kw in [
            "conflict", "diverge", "thesis", "blank slate", "sunk", "however",
            "contra", "despite", "but ", "while ", "yet ", "watch", "risk"
        ]):
            cleaned.append(s)
    return cleaned[:2] if cleaned else [_clean_step(chain[-1])][:1]


def _clean_step(step: str) -> str:
    """Strip 'Step N — Label:' or 'Step N:' prefix for cleaner prose."""
    if not step:
        return ""
    import re
    # Match: "Step N — anything up to the colon:" (handles hyphens, slashes in label)
    step = re.sub(r"^Step\s+\d+\s*[\u2014\-]+\s*[^:]+:\s*", "", step).strip()
    # Fallback: "Step N:" with no label
    step = re.sub(r"^Step\s+\d+\s*:\s*", "", step).strip()
    return step


def _direction_label(direction: str) -> str:
    d = (direction or "").lower().strip()
    if "bull" in d:
        return "↑ Bullish"
    if "bear" in d:
        return "↓ Bearish"
    return "→ Neutral"


def _extract_pnl_from_notes(notes: str, brief: dict) -> Optional[float]:
    """Try to extract the P&L percentage from blank_slate_notes."""
    import re
    if notes:
        m = re.search(r"(-?\d+\.?\d*)%", notes)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None


def _ordinal(n: Optional[float]) -> str:
    """Return '31st percentile', '42nd percentile', etc."""
    if n is None:
        return "N/A percentile"
    i = int(n)
    suffix = "th" if 11 <= (i % 100) <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(i % 10, "th")
    return f"{i}{suffix} percentile"


def _to_dict(obj: Any) -> dict:
    """Convert dataclass/object to dict safely."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return {}


def _footer() -> List[str]:
    return [
        "*Report generated by HMAS — Hierarchical Multi-Agent Investment System*",
        "*This brief supports investment decisions. The final choice belongs to the investor.*",
        "",
    ]


# ── V2 Scout Report ───────────────────────────────────────────────────────────

def _build_scout_v2_brief(result: Dict[str, Any]) -> str:
    ts = result.get("timestamp", "")[:19].replace("T", " ")
    selection = result.get("selection", {})
    top5 = selection.get("top5", [])
    macro = result.get("macro_chain", {})
    universe = result.get("universe", {})
    elapsed = result.get("elapsed_seconds", 0)

    L = [
        "# HMAS Scout Report — India Equity Opportunities",
        f"*{ts}  |  {len(top5)} opportunities selected  |  {elapsed:.0f}s*",
        "",
        "---",
        "",
    ]

    # Macro regime
    regime = macro.get("market_regime", "unknown").upper()
    conf = macro.get("regime_confidence", "?")
    causal = macro.get("causal_chain", "")
    overlay = macro.get("india_overlay", {})
    explore = macro.get("explore_themes", [])
    avoid = macro.get("avoid_themes", [])

    L += ["## Market Regime", f"**{regime}** ({conf} confidence)", ""]
    if causal:
        L += [f"> {causal}", ""]
    if overlay:
        L += [
            "| | |", "|---|---|",
            f"| **Rupee** | {overlay.get('rupee_outlook','?')} |",
            f"| **RBI stance** | {overlay.get('rbi_stance','?')} |",
            f"| **FII sentiment** | {overlay.get('fii_sentiment','?')} |",
            f"| **PE impact** | {overlay.get('pe_impact','?')} |",
            "",
        ]
    if explore:
        L += [f"**Explore this week:** {', '.join(explore)}", ""]
    if avoid:
        L += [f"**Avoid this week:** {', '.join(avoid)}", ""]
    key_risk = overlay.get("key_risk", "")
    if key_risk:
        L += [f"> **Key Risk:** {key_risk}", ""]

    # Universe stats
    raw_ct = universe.get("raw_count", 0)
    ver_ct = universe.get("verified_count", 0)
    fallback = universe.get("fallback_used", False)
    tickers = universe.get("verified_tickers", [])
    fb_note = " *(fallback sector map used)*" if fallback else ""
    L += [
        "", "---", "",
        "## Research Universe",
        f"{raw_ct} raw candidates → **{ver_ct} verified**{fb_note}",
        "",
        f"Stocks researched: {', '.join(tickers) if tickers else 'None'}",
        "",
    ]

    # Top 5
    if not top5:
        L += ["---", "", "## Top 5", "*No opportunities selected this week.*", ""]
        L += _footer()
        return "\n".join(L)

    L += ["---", "", "## This Week's Top 5 Opportunities", ""]

    rec_labels = {
        "BUY_NOW": "🟢 BUY NOW",
        "WATCH_CLOSELY": "🟡 WATCH — trigger near",
        "MONITOR_FOR_LATER": "⚪ Monitor for later",
    }
    conv_icons = {"high": "●●●", "medium": "●●○", "low": "●○○"}

    for item in top5:
        rank = item.get("rank", "?")
        ticker = item.get("ticker", "?")
        rec = item.get("recommendation", "MONITOR_FOR_LATER")
        conviction = item.get("conviction", "?")
        score = item.get("final_score", "?")
        story = item.get("story", "")
        entry = item.get("entry_zone", "N/A")
        stop = item.get("stop_loss", "N/A")
        horizon = item.get("time_horizon", "N/A")
        risk = item.get("key_risk", "")
        why = item.get("why_selected", "")
        sb = item.get("score_breakdown", {})

        L += [
            f"### #{rank} — {ticker}",
            f"{rec_labels.get(rec, rec)}  |  Conviction: {conv_icons.get(conviction, conviction)} {conviction}  |  Score: **{score}/100**",
            "",
        ]
        if story:
            L += [story, ""]

        L += ["| | |", "|---|---|",
              f"| **Entry zone** | {entry} |",
              f"| **Stop loss** | {stop} |",
              f"| **Horizon** | {horizon} |"]
        if risk:
            L += [f"| **Key risk** | {risk} |"]
        if why:
            L += [f"| **Why selected** | {why} |"]
        L += [""]

        if sb:
            L += [
                "| Score Component | Points |", "|---|---|",
                f"| Macro alignment (30 max) | {sb.get('macro_alignment','?')} |",
                f"| Fundamentals (25 max) | {sb.get('fundamentals','?')} |",
                f"| Technical setup (25 max) | {sb.get('technical_setup','?')} |",
                f"| Momentum/quant (20 max) | {sb.get('momentum','?')} |",
            ]
            if sb.get("history_boost"):
                L += [f"| History boost | +{sb['history_boost']} |"]
            L += [""]

    # Selection reasoning
    sel_reasoning = selection.get("selection_reasoning", [])
    if sel_reasoning:
        L += ["---", "", "## Selection Reasoning", ""]
        for r in sel_reasoning:
            L.append(f"- {r}")
        L.append("")

    # Full research notes (all stocks)
    all_stories = result.get("stories", [])
    if all_stories:
        opp_order = {"macro_tailwind": 0, "value_play": 1, "momentum": 2, "defensive": 3, "avoid": 4}
        all_stories = sorted(all_stories, key=lambda s: (opp_order.get(s.get("opportunity_type","avoid"), 5), -s.get("score", 0)))
        L += ["---", "", "## Full Research Notes (all stocks analysed)", ""]
        for s in all_stories:
            t = s.get("ticker", "?")
            score = s.get("score", 0)
            opp = s.get("opportunity_type", "avoid").replace("_", " ").upper()
            conv = s.get("conviction", "low")
            story = s.get("story", "")
            entry = s.get("entry_zone", "N/A")
            stop = s.get("stop_loss", "N/A")
            horizon = s.get("time_horizon", "N/A")
            tech = s.get("technicals_summary", "")
            risk = s.get("key_risk", "")
            macro = s.get("macro_alignment", "")
            L += [f"### {t}  —  {opp}  (score {score:.0f}/100, {conv} conviction)", ""]
            if macro:
                L += [f"*{macro}*", ""]
            if story:
                L += [story, ""]
            if entry != "AVOID":
                L += [f"**Entry:** {entry}  |  **Stop:** {stop}  |  **Horizon:** {horizon}", ""]
            if tech:
                L += [f"**Technicals:** {tech}", ""]
            if risk:
                L += [f"> **Key risk:** {risk}", ""]

    L += ["---", ""]
    L += _footer()
    return "\n".join(L)


# ── V2 Portfolio Report ───────────────────────────────────────────────────────

def _build_portfolio_v2_brief(result: Dict[str, Any]) -> str:
    ts = result.get("timestamp", "")[:19].replace("T", " ")
    advisor = result.get("advisor", {})
    holding_actions = result.get("holding_actions", [])
    macro = result.get("macro_chain", {})
    elapsed = result.get("elapsed_seconds", 0)

    L = [
        "# HMAS Portfolio Review",
        f"*{ts}  |  {len(holding_actions)} holding(s) reviewed  |  {elapsed:.0f}s*",
        "",
        "---",
        "",
    ]

    # Macro regime
    regime = macro.get("market_regime", "unknown").upper()
    conf = macro.get("regime_confidence", "?")
    causal = macro.get("causal_chain", "")
    overlay = macro.get("india_overlay", {})
    explore = macro.get("explore_themes", [])
    avoid = macro.get("avoid_themes", [])

    L += ["## Market Regime", f"**{regime}** ({conf} confidence)", ""]
    if causal:
        L += [f"> {causal}", ""]
    if explore:
        L += [f"**Explore themes:** {', '.join(explore)}", ""]
    if avoid:
        L += [f"**Avoid themes:** {', '.join(avoid)}", ""]

    macro_overlay_summary = advisor.get("macro_overlay_summary", "")
    if macro_overlay_summary:
        L += ["", f"> **Macro Overlay:** {macro_overlay_summary}", ""]

    # Per-holding decisions
    actions = advisor.get("holdings_actions", [])
    if actions:
        L += ["---", "", "## Portfolio Decisions", ""]
        action_icons = {
            "HOLD": "✅ HOLD", "ADD": "➕ ADD", "TRIM": "✂️ TRIM",
            "EXIT": "🔴 EXIT", "HOLD_WATCH": "⏳ HOLD & WATCH",
        }

        for a in actions:
            ticker = a.get("ticker", "?")
            action = a.get("confirmed_action", "HOLD")
            bst = a.get("blank_slate_test", "PASS")
            pnl = a.get("pnl_pct", 0)
            pnl_str = f"{pnl:+.1f}%" if isinstance(pnl, (int, float)) else "N/A"
            narrative = a.get("narrative", "")
            macro_align = a.get("macro_overlay", "")
            best_move = a.get("best_move_now", "")
            recovery = a.get("recovery_path", "")
            upgrade = a.get("upgrade_trigger", "")
            downgrade = a.get("downgrade_trigger", "")

            icon = action_icons.get(action, action)
            L += [f"### {ticker}  —  {icon}", ""]

            bst_label = "✅ PASS" if bst == "PASS" else "⚠️ FAIL"
            L += ["| | |", "|---|---|",
                  f"| **P&L** | {pnl_str} |",
                  f"| **Fresh Buyer Test** | {bst_label} |"]
            L += [""]

            if best_move:
                L += [f"**Best Move Now:** {best_move}", ""]
            if narrative:
                L += [narrative, ""]
            if recovery:
                L += [f"**Recovery Path:** {recovery}", ""]
            if upgrade:
                L += [f"**Add more when:** {upgrade}", ""]
            if downgrade:
                L += [f"**Exit if:** {downgrade}", ""]
            if macro_align:
                L += [f"*Macro: {macro_align}*", ""]

    # Gold profit-taking analysis
    gold = advisor.get("gold_profit_taking", {})
    if gold:
        L += ["---", "", "## Gold Position Analysis", ""]
        rec = gold.get("recommendation", "")
        reasoning = gold.get("reasoning", "")
        specific = gold.get("specific_action", "")
        if rec:
            L += [f"**Recommendation:** {rec}", ""]
        if reasoning:
            L += [reasoning, ""]
        if specific:
            L += [f"> {specific}", ""]

    # Rebalancing plan
    rebal = advisor.get("rebalancing_plan", "")
    if rebal and rebal != "Portfolio is reasonably balanced":
        L += ["---", "", "## Rebalancing Plan", "", rebal, ""]

    # 30-day action checklist
    checklist = advisor.get("next_30_days_checklist", [])
    if checklist:
        L += ["---", "", "## Next 30 Days — Action Checklist", ""]
        for item in checklist:
            L += [f"- {item}"]
        L += [""]

    # Concentration risks
    risks = advisor.get("concentration_risks", [])
    if risks:
        L += ["---", "", "## Concentration Risks", ""]
        for r in risks:
            L += [f"- **{r.get('factor','?')}** ({', '.join(r.get('exposed_tickers',[]))}): {r.get('risk','')}", ""]

    # Scout cross-reference
    crossref = advisor.get("scout_crossref", {})
    gaps = crossref.get("gap_fillers", [])
    overweights = crossref.get("overweight_warnings", [])
    if gaps or overweights:
        L += ["---", "", "## Scout Cross-Reference", ""]
        for g in gaps:
            L += [f"- 🟢 **Gap filler:** {g}"]
        for o in overweights:
            L += [f"- ⚠️ **Overweight warning:** {o}"]
        L += [""]

    # Sunk cost summary
    scs = advisor.get("sunk_cost_summary", {})
    if scs and scs.get("fail_count", 0) > 0:
        L += [
            "---", "", "## Sunk Cost Summary", "",
            f"**{scs.get('fail_count',0)} holding(s) fail the blank-slate test:** "
            f"{', '.join(scs.get('affected_tickers', []))}",
            "",
            scs.get("note", ""),
            "",
        ]

    # Portfolio-level advice
    advice = advisor.get("portfolio_level_advice", "")
    if advice:
        L += ["---", "", "## Portfolio-Level Advice", "", advice, ""]

    L += ["---", ""]
    L += _footer()
    return "\n".join(L)
