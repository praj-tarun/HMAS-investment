"""
dashboard.py — HMAS Investment Dashboard
Run: streamlit run dashboard.py

Three top-level tabs:
  📋 Portfolio  — latest portfolio_v2 report + history
  🔍 Scout      — latest scout_v2 report + history
  🎮 Simulation — tracks recommendation accuracy over time
"""

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from collections import Counter
from typing import Optional, Dict, Any, List

import streamlit as st

PROJECT_ROOT = Path(__file__).parent

st.set_page_config(
    page_title="HMAS Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="📈",
)

# ── Styles ──────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.action-hold   { border-left: 5px solid #16a34a !important; }
.action-add    { border-left: 5px solid #2563eb !important; }
.action-trim   { border-left: 5px solid #d97706 !important; }
.action-watch  { border-left: 5px solid #9333ea !important; }
.action-exit   { border-left: 5px solid #dc2626 !important; }
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 0.78em; font-weight: 700; letter-spacing: 0.03em;
}
.b-hold  { background:#dcfce7; color:#15803d; }
.b-add   { background:#dbeafe; color:#1d4ed8; }
.b-trim  { background:#fef3c7; color:#92400e; }
.b-watch { background:#f3e8ff; color:#6b21a8; }
.b-exit  { background:#fee2e2; color:#b91c1c; }
.price-box {
    text-align:center; padding:8px; background:#f9fafb;
    border-radius:8px; border:1px solid #e5e7eb; color:#111827;
}
.price-label { font-size:0.72em; color:#6b7280; text-transform:uppercase; }
.price-value { font-size:1.2em; font-weight:700; color:#111827; }
.check-item {
    background:#f0fdf4; border-left:3px solid #16a34a; padding:8px 14px;
    margin-bottom:6px; border-radius:0 6px 6px 0; font-size:0.9em; color:#166534;
}
.sim-good { color:#16a34a; font-weight:700; }
.sim-bad  { color:#dc2626; font-weight:700; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def badge(text: str, kind: str) -> str:
    return f'<span class="badge b-{kind}">{text}</span>'

def action_badge(action: str) -> str:
    icons = {"HOLD": "✅ HOLD", "ADD": "➕ ADD", "TRIM": "✂️ TRIM",
             "HOLD_WATCH": "⏳ WATCH", "EXIT": "🔴 EXIT"}
    kinds = {"HOLD": "hold", "ADD": "add", "TRIM": "trim",
             "HOLD_WATCH": "watch", "EXIT": "exit"}
    return badge(icons.get(action, action), kinds.get(action, "watch"))

def pnl_color(pnl) -> str:
    return "#16a34a" if (pnl or 0) >= 0 else "#dc2626"

def load_report(mode: str) -> Optional[Dict[str, Any]]:
    """Load latest report for a given mode from the mode-specific shortcut file."""
    path = PROJECT_ROOT / f".last_report_{mode}.json"
    if not path.exists():
        # Fall back to legacy .last_report.json if the mode matches
        legacy = PROJECT_ROOT / ".last_report.json"
        if legacy.exists():
            try:
                r = json.loads(legacy.read_text(encoding="utf-8"))
                if mode in r.get("mode", ""):
                    return r
            except Exception:
                pass
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def load_portfolio_memory() -> Dict:
    p = PROJECT_ROOT / "portfolio_memory.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}

def list_reports(mode: str, limit: int = 20) -> List[Dict]:
    """List historical reports for a mode."""
    folder = PROJECT_ROOT / "reports" / mode
    if not folder.exists():
        return []
    files = sorted(folder.glob("*.json"), reverse=True)[:limit]
    results = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append({"filename": f.stem, "timestamp": data.get("timestamp",""), "data": data})
        except Exception:
            continue
    return results


# ── Run from UI ─────────────────────────────────────────────────────────────────
# Strategy: write subprocess stdout to a log file so the main thread can read it
# during polling. Use a .status file instead of session_state for cross-thread
# status (avoids ScriptRunContext warnings entirely).

_REPORTS_DIR = PROJECT_ROOT / "reports"

def _log_file(mode: str) -> Path:
    return _REPORTS_DIR / f"running_{mode}.log"

def _status_file(mode: str) -> Path:
    return _REPORTS_DIR / f"running_{mode}.status"

def _get_run_status(mode: str) -> str:
    """Read status from file (written by background thread)."""
    f = _status_file(mode)
    if not f.exists():
        return "idle"
    try:
        return f.read_text(encoding="utf-8").strip()
    except Exception:
        return "idle"

def _set_run_status(mode: str, status: str):
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _status_file(mode).write_text(status, encoding="utf-8")

def _get_log_lines(mode: str) -> list:
    f = _log_file(mode)
    if not f.exists():
        return []
    try:
        return f.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

def _run_analysis(command: str, mode: str):
    """Background thread: runs CLI command, streams output to a log file."""
    import os
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log = _log_file(mode)
    log.write_text("", encoding="utf-8")   # clear previous log
    _set_run_status(mode, "running")
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"   # force UTF-8 stdout in subprocess
        env["PYTHONUNBUFFERED"] = "1"        # disable Python output buffering (Windows fix)
        proc = subprocess.Popen(
            [sys.executable, "-u", "run.py", command],  # -u = unbuffered
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=0,
            encoding="utf-8", errors="replace",
            env=env,
        )
        with open(log, "w", encoding="utf-8", buffering=1) as lf:
            for line in proc.stdout:
                lf.write(line)
                lf.flush()
        proc.wait()
        _set_run_status(mode, "done" if proc.returncode == 0 else "error")
    except Exception as exc:
        with open(log, "a", encoding="utf-8") as lf:
            lf.write(f"\n[ERROR] {exc}\n")
        _set_run_status(mode, "error")


def _parse_phases(lines: list, mode: str) -> list:
    """
    Parse log lines into structured phase entries for visual display.
    Returns list of {phase, label, status, detail_lines}.
    """
    # Define expected phases per mode
    if mode == "portfolio":
        phases = [
            ("Phase 0", "Intelligence Gathering (4 agents, parallel)"),
            ("Phase 1", "Macro Chain Reasoning"),
            ("Phase 2", "Per-Holding Research (parallel)"),
            ("Phase 3", "Portfolio Advisor Synthesis"),
        ]
    else:
        phases = [
            ("Phase 0", "Intelligence Gathering (4 agents, parallel)"),
            ("Phase 1", "Macro Chain Reasoning"),
            ("Phase 2A", "Web Search Universe"),
            ("Phase 2B", "Source Verification"),
            ("Phase 3", "Stock Research (parallel)"),
            ("Phase 4", "Top 5 Selection"),
        ]

    phase_results = []
    current_phase_idx = -1
    phase_detail: dict = {}   # idx -> [lines]

    for ln in lines:
        stripped = ln.strip()
        for i, (key, label) in enumerate(phases):
            if f"[{key}]" in ln or f"[{key} " in ln:
                if i > current_phase_idx:
                    current_phase_idx = i
                phase_detail.setdefault(i, [])
                break
        else:
            # Line belongs to current phase
            if current_phase_idx >= 0 and stripped and not stripped.startswith("[Phase"):
                phase_detail.setdefault(current_phase_idx, [])
                phase_detail[current_phase_idx].append(stripped)

    for i, (key, label) in enumerate(phases):
        if i < current_phase_idx:
            status_ph = "done"
        elif i == current_phase_idx:
            status_ph = "running"
        else:
            status_ph = "pending"
        phase_results.append({
            "key": key, "label": label, "status": status_ph,
            "lines": phase_detail.get(i, []),
        })
    return phase_results


def render_run_controls(mode: str, command: str, label: str):
    """Render run button + structured phase progress display."""
    col_btn, col_status = st.columns([1, 4])
    with col_btn:
        if st.button(f"▶ Run {label}", use_container_width=True, type="primary"):
            _set_run_status(mode, "starting")
            t = threading.Thread(target=_run_analysis, args=(command, mode), daemon=True)
            t.start()

    status = _get_run_status(mode)
    lines  = _get_log_lines(mode)

    with col_status:
        if status in ("running", "starting"):
            st.info(f"⏳ Analysis running — refreshing every 3s")
        elif status == "done":
            st.success("✅ Complete! Click **Load new report** below.")
        elif status == "error":
            st.error("❌ Failed — see error log below")

    # ── Phase progress display ──────────────────────────────────────────────
    if status in ("running", "starting", "done", "error") and lines:

        st.markdown("**Agent Pipeline Progress:**")
        phases = _parse_phases(lines, mode)
        icon = {"done": "✅", "running": "⏳", "pending": "⬜"}
        color = {"done": "#16a34a", "running": "#2563eb", "pending": "#6b7280"}

        for ph in phases:
            ph_icon  = icon[ph["status"]]
            ph_color = color[ph["status"]]
            detail   = ph["lines"]

            # Show last meaningful line as live activity
            last_line = ""
            for ln in reversed(detail):
                if ln and not ln.startswith("---") and len(ln) > 5:
                    last_line = ln[:120]
                    break

            st.markdown(
                f'<div style="padding:6px 12px;margin:3px 0;border-left:3px solid {ph_color};'
                f'border-radius:0 6px 6px 0;background:#f8fafc">'
                f'<span style="font-size:1em">{ph_icon}</span> '
                f'<b style="color:{ph_color}">[{ph["key"]}]</b> '
                f'<span style="color:#374151">{ph["label"]}</span>'
                + (f'<br><span style="font-size:0.82em;color:#6b7280;margin-left:1.5em">{last_line}</span>'
                   if last_line and ph["status"] in ("running", "done") else "")
                + "</div>",
                unsafe_allow_html=True,
            )
            # Show last 5 detail lines for the running phase
            if ph["status"] == "running" and detail:
                with st.expander("  Show live agent output", expanded=True):
                    for ln in detail[-15:]:
                        if ln.strip():
                            st.markdown(
                                f'<div style="font-size:0.83em;color:#374151;'
                                f'font-family:monospace;padding:1px 8px">{ln}</div>',
                                unsafe_allow_html=True,
                            )

        # Full raw log always available
        with st.expander("📋 Full log", expanded=(status == "error")):
            st.code("\n".join(lines), language=None)

        if status == "done":
            if st.button("Load new report", key=f"load_{mode}", type="primary"):
                _set_run_status(mode, "idle")
                st.rerun()
        elif status == "error":
            if st.button("Reset", key=f"reset_{mode}"):
                _set_run_status(mode, "idle")
                st.rerun()

    st.markdown("")
    if st.button("🔄 Refresh", key=f"refresh_{mode}"):
        st.rerun()

    # Auto-poll while running (Streamlit polling pattern)
    if status in ("running", "starting"):
        time.sleep(3)
        st.rerun()


# ── Portfolio report renderer ───────────────────────────────────────────────────

def render_portfolio(report: Dict[str, Any]):
    macro        = report.get("macro_chain", {})
    intel        = report.get("intel_packets", {})
    holding_acts = report.get("holding_actions", [])
    advisor      = report.get("advisor", {})
    adv_actions  = advisor.get("holdings_actions", [])
    memory       = load_portfolio_memory()
    mem_holdings = {h["ticker"]: h for h in memory.get("holdings", [])}

    # Build merged dict: ticker → research + advisor fields
    research_by_ticker = {h["ticker"]: h for h in holding_acts}
    merged = {}
    for adv in adv_actions:
        t = adv.get("ticker", "")
        res = research_by_ticker.get(t, {})
        merged[t] = {**res, **adv}
    for t, res in research_by_ticker.items():
        if t not in merged:
            merged[t] = res

    # ── Regime banner ────────────────────────────────────────────────────────
    regime       = macro.get("market_regime", "?").upper()
    regime_conf  = macro.get("regime_confidence", "?")
    causal       = macro.get("causal_chain", "")
    overlay      = macro.get("india_overlay", {})
    regime_bg    = {"RISK-OFF":"#fee2e2","RISK-ON":"#dcfce7","MIXED":"#fef3c7","SECTOR-ROTATION":"#e0f2fe"}.get(regime,"#f3f4f6")
    regime_fg    = {"RISK-OFF":"#991b1b","RISK-ON":"#14532d","MIXED":"#92400e","SECTOR-ROTATION":"#0c4a6e"}.get(regime,"#374151")
    st.markdown(
        f'<div style="background:{regime_bg};border-radius:10px;padding:12px 18px;margin-bottom:12px">'
        f'<span style="color:{regime_fg};font-size:1.1em;font-weight:700">Macro Regime: {regime}</span>'
        f'&nbsp;&nbsp;<span style="color:{regime_fg};font-size:0.85em">{regime_conf} confidence</span>'
        + (f'<br><span style="color:{regime_fg};font-size:0.83em;opacity:0.9">{causal[:220]}...</span>' if causal else "")
        + "</div>", unsafe_allow_html=True,
    )

    # ── Summary metrics ───────────────────────────────────────────────────────
    total_invested = sum(h.get("entry_price",0)*h.get("quantity",1) for h in mem_holdings.values())
    total_current  = sum(h.get("current_price",0)*h.get("quantity",1) for h in mem_holdings.values())
    blended_pnl    = ((total_current-total_invested)/total_invested*100) if total_invested else 0
    pnl_diff       = total_current - total_invested
    pnl_delta_str  = f"{'-' if pnl_diff<0 else '+'}Rs.{abs(pnl_diff):,.0f}"
    ts             = report.get("timestamp","")[:19].replace("T"," ")
    elapsed        = report.get("elapsed_seconds", 0)

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("Holdings",       len(merged))
    c2.metric("Total Invested", f"Rs.{total_invested/1000:.1f}K" if total_invested else "—")
    c3.metric("Current Value",  f"Rs.{total_current/1000:.1f}K"  if total_current  else "—")
    c4.metric("Portfolio P&L",  f"{blended_pnl:+.1f}%",  delta=pnl_delta_str, delta_color="normal")
    c5.metric("Regime",         regime)
    c6.metric("Run time",       f"{elapsed:.0f}s  ·  {ts[:10]}")
    st.divider()

    # ── Sub-tabs ──────────────────────────────────────────────────────────────
    tab_h, tab_plan, tab_macro, tab_agents, tab_raw = st.tabs([
        "📋 Holdings", "🗓 30-Day Plan", "🌐 Macro", "🧠 Agent Thinking", "🗂 Raw JSON",
    ])

    # ── Holdings ──────────────────────────────────────────────────────────────
    with tab_h:
        advice = advisor.get("portfolio_level_advice", "")
        if advice:
            st.info(f"**Portfolio View:** {advice}")

        for ticker, h in merged.items():
            action      = h.get("confirmed_action") or h.get("action", "HOLD")
            pnl         = h.get("pnl_pct", 0)
            narrative   = h.get("narrative", "")
            best_move   = h.get("best_move_now", "")
            recovery    = h.get("recovery_path") or h.get("recovery_scenario", "")
            upgrade_t   = h.get("upgrade_trigger", "")
            downgrade_t = h.get("downgrade_trigger", "")
            macro_ov    = h.get("macro_overlay") or h.get("macro_alignment", "")
            technicals  = h.get("technicals_summary", "")
            fundamentals= h.get("fundamentals_summary", "")
            bst         = h.get("blank_slate_test", "PASS")
            key_risk    = h.get("key_risk", "")
            reasoning   = h.get("reasoning_chain", [])
            news        = h.get("news_highlights", [])
            live_price  = h.get("current_price", 0)

            mem          = mem_holdings.get(ticker, {})
            invested_val = mem.get("entry_price",0) * mem.get("quantity",1)
            thesis_text  = mem.get("thesis", "")
            is_proxy     = "proxy ETF" in thesis_text or "MF holding" in thesis_text

            action_css = {"HOLD":"action-hold","ADD":"action-add","TRIM":"action-trim",
                          "HOLD_WATCH":"action-watch","EXIT":"action-exit"}.get(action,"action-watch")

            # Card header
            h_left, h_right = st.columns([3, 2])
            with h_left:
                proxy_note = " *(MF proxy)*" if is_proxy else ""
                st.markdown(
                    f'<div class="{action_css}" style="padding-left:8px">'
                    f'<h4 style="margin:4px 0">{ticker}{proxy_note} &nbsp;'
                    + action_badge(action)
                    + ("&nbsp;" + badge("Sunk Cost Risk","b-exit") if bst=="FAIL" else "")
                    + "</h4></div>",
                    unsafe_allow_html=True,
                )
                if is_proxy and thesis_text:
                    m = re.search(r"Schemes?: (.+?)(?:\||$)", thesis_text)
                    if m:
                        st.caption(f"Represents: {m.group(1).strip()[:100]}")
            with h_right:
                p1, p2, p3 = st.columns(3)
                pc = pnl_color(pnl)
                p1.markdown(
                    f'<div class="price-box"><div class="price-label">P&L</div>'
                    f'<div class="price-value" style="color:{pc}">{"+" if (pnl or 0)>=0 else ""}{pnl:.1f}%</div></div>',
                    unsafe_allow_html=True,
                )
                if invested_val:
                    p2.markdown(
                        f'<div class="price-box"><div class="price-label">Invested</div>'
                        f'<div class="price-value">Rs.{invested_val/1000:.1f}K</div></div>',
                        unsafe_allow_html=True,
                    )
                if live_price:
                    label = "ETF Price" if is_proxy else "Live Price"
                    p3.markdown(
                        f'<div class="price-box"><div class="price-label">{label}</div>'
                        f'<div class="price-value">Rs.{live_price:.2f}</div></div>',
                        unsafe_allow_html=True,
                    )

            # Best Move Now
            if best_move:
                st.markdown(
                    f'<div style="background:#f0fdf4;border-left:4px solid #16a34a;'
                    f'padding:8px 14px;border-radius:0 6px 6px 0;margin:6px 0;color:#166534">'
                    f'<b>Best Move Now:</b> {best_move}</div>',
                    unsafe_allow_html=True,
                )
            if narrative:
                st.markdown(narrative)

            # Triggers
            if recovery or upgrade_t or downgrade_t:
                t1, t2, t3 = st.columns(3)
                if recovery:
                    t1.markdown(
                        f'<div class="price-box" style="text-align:left;padding:10px">'
                        f'<div class="price-label">Recovery Path</div>'
                        f'<div style="font-size:0.85em;margin-top:4px;color:#374151">{recovery}</div></div>',
                        unsafe_allow_html=True,
                    )
                if upgrade_t:
                    t2.markdown(
                        f'<div class="price-box" style="text-align:left;padding:10px;border-color:#bbf7d0">'
                        f'<div class="price-label" style="color:#15803d">Buy / Add Signal</div>'
                        f'<div style="font-size:0.85em;margin-top:4px;color:#374151">{upgrade_t}</div></div>',
                        unsafe_allow_html=True,
                    )
                if downgrade_t:
                    t3.markdown(
                        f'<div class="price-box" style="text-align:left;padding:10px;border-color:#fca5a5">'
                        f'<div class="price-label" style="color:#dc2626">Exit Signal</div>'
                        f'<div style="font-size:0.85em;margin-top:4px;color:#374151">{downgrade_t}</div></div>',
                        unsafe_allow_html=True,
                    )

            # Gold advice inline for GOLDBEES
            if ticker == "GOLDBEES.NS":
                gold = advisor.get("gold_profit_taking", {})
                if gold:
                    rec_g   = gold.get("recommendation", "")
                    spec_g  = gold.get("specific_action", "")
                    rsn_g   = gold.get("reasoning", "")
                    gbg = {"TRIM_PARTIAL":"#fef3c7","TRIM_SIGNIFICANT":"#fee2e2","HOLD_FULL":"#dcfce7"}.get(rec_g,"#f3f4f6")
                    gfg = {"TRIM_PARTIAL":"#92400e","TRIM_SIGNIFICANT":"#b91c1c","HOLD_FULL":"#14532d"}.get(rec_g,"#374151")
                    glbl= {"TRIM_PARTIAL":"✂️ Trim Partial","TRIM_SIGNIFICANT":"🔴 Trim Significantly","HOLD_FULL":"✅ Hold Full"}.get(rec_g,rec_g)
                    st.markdown(
                        f'<div style="background:{gbg};border-radius:8px;padding:10px 16px;margin:8px 0;color:{gfg};font-weight:600">'
                        f'Gold Hedge Advice: {glbl}</div>', unsafe_allow_html=True,
                    )
                    if spec_g:
                        st.markdown(
                            f'<div style="background:#fefce8;border-left:4px solid #ca8a04;'
                            f'padding:8px 14px;border-radius:0 6px 6px 0;margin:4px 0;color:#713f12">'
                            f'<b>Specific Action:</b> {spec_g}</div>', unsafe_allow_html=True,
                        )
                    if rsn_g:
                        st.caption(rsn_g)

            if macro_ov:
                st.caption(f"**Macro:** {macro_ov}")

            # Thinking expander
            with st.expander("🔍 Agent thinking", expanded=False):
                if technicals:
                    st.markdown(f"**Technicals:** {technicals}")
                if fundamentals:
                    st.markdown(f"**Fundamentals:** {fundamentals}")
                if key_risk:
                    st.warning(f"**Key risk:** {key_risk}")
                if news:
                    st.markdown("**News highlights:**")
                    for n in news:
                        st.markdown(f"- {n}")
                if reasoning:
                    st.markdown("**Step-by-step reasoning:**")
                    for step in reasoning:
                        st.markdown(
                            f'<div style="background:#f8fafc;border-left:3px solid #6366f1;'
                            f'padding:6px 12px;margin:3px 0;border-radius:0 4px 4px 0;'
                            f'font-size:0.87em;color:#1e1b4b">{step}</div>',
                            unsafe_allow_html=True,
                        )
            st.divider()

        # Concentration risks
        for r in advisor.get("concentration_risks", []):
            tickers_str = ", ".join(r.get("exposed_tickers", []))
            st.warning(f"⚠️ **{r.get('factor','?')}** ({tickers_str}) — {r.get('risk','')}")

    # ── 30-Day Plan ───────────────────────────────────────────────────────────
    with tab_plan:
        checklist = advisor.get("next_30_days_checklist", [])
        rebal     = advisor.get("rebalancing_plan", "")
        scs       = advisor.get("sunk_cost_summary", {})

        if checklist:
            st.subheader("Your Next 30 Days — Action Plan")
            st.caption("IF/THEN triggers. Check these every week.")
            for item in checklist:
                if "THEN" in item.upper():
                    parts = item.split("THEN", 1) if "THEN" in item else item.split("then", 1)
                    trigger = parts[0].lstrip("IFif").strip(" ,:")
                    action  = parts[1].strip() if len(parts) > 1 else ""
                    st.markdown(
                        f'<div class="check-item"><span style="opacity:0.7">IF</span> <b>{trigger}</b>'
                        f'<br><span style="color:#15803d">→ THEN</span> {action}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(f'<div class="check-item">{item}</div>', unsafe_allow_html=True)
        else:
            st.caption("No checklist — run portfolio analysis first.")

        if rebal and "reasonably balanced" not in rebal.lower():
            st.markdown("---")
            st.subheader("Rebalancing Suggestion")
            st.info(rebal)

        if scs and scs.get("fail_count", 0) > 0:
            st.markdown("---")
            affected = ", ".join(scs.get("affected_tickers", []))
            st.error(
                f"**Sunk Cost Alert — {scs.get('fail_count',0)} holding(s) fail fresh-buyer test:** {affected}\n\n"
                + scs.get("note", "")
            )

    # ── Macro ─────────────────────────────────────────────────────────────────
    with tab_macro:
        st.subheader(f"Regime: {regime}  ·  {regime_conf} confidence")
        if causal:
            st.info(f"**Causal chain:** {causal}")
        if overlay:
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Rupee",     overlay.get("rupee_outlook","?"))
            c2.metric("RBI",       overlay.get("rbi_stance","?"))
            c3.metric("FII",       overlay.get("fii_sentiment","?"))
            c4.metric("PE Impact", overlay.get("pe_impact","?"))
        explore = macro.get("explore_themes", [])
        avoid   = macro.get("avoid_themes", [])
        if explore:
            st.markdown(f"**Explore:** {', '.join(explore)}")
        if avoid:
            st.markdown(f"**Avoid:** {', '.join(avoid)}")
        with st.expander("Macro reasoning chain"):
            for step in macro.get("reasoning_chain", []):
                st.markdown(f'<div style="border-left:3px solid #6366f1;padding:4px 12px;margin:2px 0;font-size:0.87em;color:#1e1b4b">{step}</div>', unsafe_allow_html=True)

    # ── Agent Thinking ────────────────────────────────────────────────────────
    with tab_agents:
        st.subheader("Phase 0 — Intelligence Agents")
        for key, label in [("news","📰 News Intel"),("markets","🌍 Global Markets"),("geo","🗺️ Geopolitics"),("macro","📊 Macro Data")]:
            pkt = intel.get(key)
            if not pkt:
                continue
            with st.expander(f"{label}  ·  {pkt.get('regime','?')}  ·  {pkt.get('confidence','?')}", expanded=False):
                if pkt.get("summary"):
                    st.markdown(pkt["summary"])
                for s in pkt.get("key_signals", []):
                    st.markdown(f"- {s}")
                for r in pkt.get("reasoning_chain", []):
                    st.markdown(f'<div style="border-left:3px solid #6366f1;padding:4px 12px;margin:2px 0;font-size:0.85em;color:#1e1b4b">{r}</div>', unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("Phase 1 — Macro Chain")
        with st.expander("Macro chain reasoning", expanded=False):
            for step in macro.get("reasoning_chain", []):
                st.markdown(f"- {step}")

        st.markdown("---")
        st.subheader("Phase 2 — Per-Holding Research")
        for h in holding_acts:
            t    = h.get("ticker","?")
            act  = h.get("action","?")
            pnl_h= h.get("pnl_pct",0)
            with st.expander(f"{t}  ·  {act}  ·  P&L: {pnl_h:+.1f}%", expanded=False):
                cl, cr = st.columns(2)
                cl.markdown(f"**Technicals:** {h.get('technicals_summary','—')}")
                cr.markdown(f"**Fundamentals:** {h.get('fundamentals_summary','—')}")
                st.markdown(f"**Thesis:** {h.get('thesis_status','?')}  ·  **Blank-slate:** {h.get('blank_slate_test','?')}")
                if h.get("recovery_scenario"):
                    st.markdown(f"**Recovery:** {h['recovery_scenario']}")
                if h.get("upgrade_trigger"):
                    st.success(f"Add when: {h['upgrade_trigger']}")
                if h.get("downgrade_trigger"):
                    st.error(f"Exit if: {h['downgrade_trigger']}")
                if h.get("key_risk"):
                    st.warning(f"Key risk: {h['key_risk']}")
                for n in h.get("news_highlights", []):
                    st.markdown(f"- {n}")
                for step in h.get("reasoning_chain", []):
                    st.markdown(f'<div style="border-left:3px solid #6366f1;padding:4px 12px;margin:2px 0;font-size:0.85em;color:#1e1b4b">{step}</div>', unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("Phase 3 — Portfolio Advisor")
        with st.expander("Advisor reasoning chain", expanded=False):
            for step in advisor.get("reasoning_chain", []):
                st.markdown(f'<div style="border-left:3px solid #6366f1;padding:4px 12px;margin:2px 0;font-size:0.85em;color:#1e1b4b">{step}</div>', unsafe_allow_html=True)

    # ── Raw JSON ──────────────────────────────────────────────────────────────
    with tab_raw:
        st.json(report)


# ── Scout report renderer ────────────────────────────────────────────────────────

def render_scout(report: Dict[str, Any]):
    macro     = report.get("macro_chain", {})
    intel     = report.get("intel_packets", {})
    selection = report.get("selection", {})
    universe  = report.get("universe", {})
    stories   = report.get("stories", [])
    top5      = selection.get("top5", [])
    regime    = macro.get("market_regime","?").upper()
    causal    = macro.get("causal_chain","")
    ts        = report.get("timestamp","")[:19].replace("T"," ")
    elapsed   = report.get("elapsed_seconds", 0)

    regime_bg = {"RISK-OFF":"#fee2e2","RISK-ON":"#dcfce7","MIXED":"#fef3c7","SECTOR-ROTATION":"#e0f2fe"}.get(regime,"#f3f4f6")
    regime_fg = {"RISK-OFF":"#991b1b","RISK-ON":"#14532d","MIXED":"#92400e","SECTOR-ROTATION":"#0c4a6e"}.get(regime,"#374151")
    st.markdown(
        f'<div style="background:{regime_bg};border-radius:10px;padding:12px 18px;margin-bottom:12px">'
        f'<span style="color:{regime_fg};font-size:1.1em;font-weight:700">Macro Regime: {regime}</span>'
        f'&nbsp;&nbsp;<span style="color:{regime_fg};font-size:0.85em">{macro.get("regime_confidence","?")} confidence</span>'
        + (f'<br><span style="color:{regime_fg};font-size:0.83em">{causal[:220]}...</span>' if causal else "")
        + "</div>", unsafe_allow_html=True,
    )

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Regime",     regime)
    c2.metric("Researched", universe.get("verified_count", 0))
    c3.metric("Top Picks",  len(top5))
    c4.metric("Fallback",   "Yes" if universe.get("fallback_used") else "No")
    c5.metric("Run time",   f"{elapsed:.0f}s  ·  {ts[:10]}")
    st.divider()

    tab_picks, tab_all, tab_macro_s, tab_agents_s, tab_raw_s = st.tabs([
        "🏆 Top Picks", "📊 All Research", "🌐 Macro", "🧠 Agent Thinking", "🗂 Raw JSON",
    ])

    with tab_picks:
        rec_icons = {"BUY_NOW":"🟢","WATCH_CLOSELY":"🟡","MONITOR_FOR_LATER":"⚪"}
        for item in top5:
            rank = item.get("rank","?"); ticker = item.get("ticker","?")
            rec  = item.get("recommendation","MONITOR_FOR_LATER")
            conv = item.get("conviction","?"); score = item.get("final_score","?")
            with st.expander(
                f"{rec_icons.get(rec,'⚪')} #{rank} **{ticker}**  ·  {rec}  ·  conviction:{conv}  ·  score:{score}/100",
                expanded=(rec=="BUY_NOW"),
            ):
                if item.get("story"):
                    st.markdown(item["story"])
                p1,p2,p3 = st.columns(3)
                p1.markdown(f'<div class="price-box"><div class="price-label">Entry Zone</div><div class="price-value" style="font-size:1em">{item.get("entry_zone","N/A")}</div></div>', unsafe_allow_html=True)
                p2.markdown(f'<div class="price-box" style="border-color:#fca5a5"><div class="price-label" style="color:#dc2626">Stop Loss</div><div class="price-value" style="font-size:1em;color:#dc2626">{item.get("stop_loss","N/A")}</div></div>', unsafe_allow_html=True)
                p3.markdown(f'<div class="price-box"><div class="price-label">Horizon</div><div class="price-value" style="font-size:1em">{item.get("time_horizon","N/A")}</div></div>', unsafe_allow_html=True)
                if item.get("why_selected"):
                    st.caption(f"**Why selected:** {item['why_selected']}")
                if item.get("key_risk"):
                    st.warning(f"**Key risk:** {item['key_risk']}")
                sb = item.get("score_breakdown", {})
                if sb:
                    sc = st.columns(4)
                    sc[0].metric("Macro (30)",     sb.get("macro_alignment","?"))
                    sc[1].metric("Fundamentals",   sb.get("fundamentals","?"))
                    sc[2].metric("Technicals",     sb.get("technical_setup","?"))
                    sc[3].metric("Momentum",       sb.get("momentum","?"))

        if selection.get("selection_reasoning"):
            with st.expander("Selection reasoning"):
                for r in selection["selection_reasoning"]:
                    st.markdown(f"- {r}")
        avoided = selection.get("avoided", [])
        if avoided:
            with st.expander(f"Not selected ({len(avoided)})"):
                ar = selection.get("avoided_reasons", {})
                for t in avoided:
                    st.markdown(f"- **{t}**: {ar.get(t,'Did not make top 5')}")

    with tab_all:
        order = {"macro_tailwind":0,"value_play":1,"momentum":2,"defensive":3,"avoid":4}
        type_info = {"macro_tailwind":("🟢","Macro Tailwind"),"value_play":("🔵","Value Play"),"momentum":("🟡","Momentum"),"defensive":("⚪","Defensive"),"avoid":("🔴","Avoid")}
        for s in sorted(stories, key=lambda s:(order.get(s.get("opportunity_type","avoid"),5),-s.get("score",0))):
            opp = s.get("opportunity_type","avoid"); score = s.get("score",0)
            icon_o, label_o = type_info.get(opp,("⚪",opp))
            with st.expander(f"{icon_o} **{s.get('ticker','?')}**  ·  {label_o}  ·  {score:.0f}/100  ·  {s.get('conviction','low')}", expanded=(opp in ("macro_tailwind","value_play"))):
                if s.get("story"):
                    st.markdown(s["story"])
                p1,p2,p3 = st.columns(3)
                p1.markdown(f"**Entry:** {s.get('entry_zone','N/A')}")
                p2.markdown(f"**Stop:** {s.get('stop_loss','N/A')}")
                p3.markdown(f"**Horizon:** {s.get('time_horizon','N/A')}")
                if s.get("key_risk"):
                    st.warning(f"**Key risk:** {s['key_risk']}")

    with tab_macro_s:
        st.subheader(f"Regime: {regime}  ·  {macro.get('regime_confidence','?')} confidence")
        if causal:
            st.info(causal)
        overlay = macro.get("india_overlay", {})
        if overlay:
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Rupee", overlay.get("rupee_outlook","?")); c2.metric("RBI",overlay.get("rbi_stance","?"))
            c3.metric("FII",   overlay.get("fii_sentiment","?")); c4.metric("PE",overlay.get("pe_impact","?"))
        if macro.get("explore_themes"):
            st.markdown(f"**Explore:** {', '.join(macro['explore_themes'])}")
        if macro.get("avoid_themes"):
            st.markdown(f"**Avoid:** {', '.join(macro['avoid_themes'])}")
        with st.expander("Macro reasoning chain"):
            for r in macro.get("reasoning_chain",[]):
                st.markdown(f"- {r}")

    with tab_agents_s:
        st.subheader("Phase 0 — Intelligence Agents")
        for key, label in [("news","📰 News"),("markets","🌍 Global Markets"),("geo","🗺️ Geopolitics"),("macro","📊 Macro Data")]:
            pkt = intel.get(key)
            if not pkt:
                continue
            with st.expander(f"{label}  ·  {pkt.get('regime','?')}  ·  {pkt.get('confidence','?')}"):
                if pkt.get("summary"):
                    st.markdown(pkt["summary"])
                for s in pkt.get("key_signals",[]):
                    st.markdown(f"- {s}")
        st.markdown("---")
        st.subheader("Phase 2 — Universe Discovery")
        c1,c2 = st.columns(2)
        c1.metric("Raw candidates", universe.get("raw_count",0))
        c2.metric("Verified",       universe.get("verified_count",0))
        if universe.get("verified_tickers"):
            st.markdown(f"**Researched:** {', '.join(universe['verified_tickers'])}")
        rejected = universe.get("rejected",{})
        if rejected:
            with st.expander(f"Rejected ({len(rejected)})"):
                for t,r in rejected.items():
                    st.markdown(f"- **{t}**: {r}")

    with tab_raw_s:
        st.json(report)


# ── Simulation tab renderer ──────────────────────────────────────────────────────

def render_simulation():
    """
    Show recommendation accuracy and what-if P&L from historical portfolio reports.
    Uses consecutive report pairs: what was recommended in report N, how did it perform by report N+1.
    """
    st.subheader("Recommendation Accuracy Tracker")
    st.caption(
        "Compares each run's recommended actions against the next run's P&L changes. "
        "Builds understanding of what works in each macro regime."
    )

    reports = list_reports("portfolio", limit=30)
    if len(reports) < 2:
        st.info("Need at least 2 portfolio runs to compute simulation results. Run portfolio analysis more than once.")
        if reports:
            st.caption(f"Current history: {len(reports)} run(s)")
        return

    # Build per-ticker simulation rows
    rows = []
    for i in range(len(reports) - 1):
        curr = reports[i]["data"]
        prev = reports[i + 1]["data"]

        curr_ts   = curr.get("timestamp", "")[:10]
        curr_adv  = curr.get("advisor", {}).get("holdings_actions", [])
        prev_acts = {h.get("ticker"): h for h in prev.get("holding_actions", [])}
        curr_acts = {h.get("ticker"): h for h in curr.get("holding_actions", [])}

        for adv in curr_adv:
            ticker  = adv.get("ticker", "")
            action  = adv.get("confirmed_action") or adv.get("action", "?")
            pnl_now = adv.get("pnl_pct")
            regime  = curr.get("macro_chain", {}).get("market_regime", "?").upper()

            prev_h = prev_acts.get(ticker, {})
            pnl_then = prev_h.get("pnl_pct")
            if pnl_now is None or pnl_then is None:
                continue

            pnl_change = pnl_now - pnl_then

            # Did the action make sense?
            # HOLD/HOLD_WATCH in a loss = P&L improved → good, worsened → bad
            # ADD = P&L improved → good
            # EXIT = would have locked in loss, P&L improved → bad (EXIT was wrong)
            # TRIM = P&L improved more than trimmed → debatable (just flag neutral)
            if action in ("HOLD", "HOLD_WATCH", "ADD"):
                outcome = "correct" if pnl_change >= 0 else "incorrect"
            elif action == "EXIT":
                outcome = "incorrect" if pnl_change >= 0 else "correct"
            elif action == "TRIM":
                outcome = "neutral"
            else:
                outcome = "neutral"

            rows.append({
                "date": curr_ts,
                "ticker": ticker,
                "action": action,
                "pnl_at_recommendation": pnl_then,
                "pnl_next_run": pnl_now,
                "pnl_change": pnl_change,
                "regime": regime,
                "outcome": outcome,
            })

    if not rows:
        st.info("Not enough consecutive data points yet to compare. Run portfolio analysis weekly.")
        return

    # Summary metrics
    total  = len(rows)
    correct   = sum(1 for r in rows if r["outcome"] == "correct")
    incorrect = sum(1 for r in rows if r["outcome"] == "incorrect")
    accuracy  = correct / total * 100 if total else 0

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Recommendations tracked", total)
    c2.metric("Correct calls",   correct)
    c3.metric("Incorrect calls", incorrect)
    c4.metric("Accuracy", f"{accuracy:.0f}%")

    st.divider()

    # Per-ticker accuracy
    st.subheader("Per-Ticker Accuracy")
    tickers_seen = list(dict.fromkeys(r["ticker"] for r in rows))
    for ticker in tickers_seen:
        ticker_rows = [r for r in rows if r["ticker"] == ticker]
        t_correct   = sum(1 for r in ticker_rows if r["outcome"] == "correct")
        t_total     = len(ticker_rows)
        t_acc       = t_correct / t_total * 100 if t_total else 0
        with st.expander(f"**{ticker}**  ·  accuracy: {t_acc:.0f}%  ·  {t_total} calls", expanded=False):
            for r in ticker_rows:
                chg   = r["pnl_change"]
                color = "#16a34a" if r["outcome"]=="correct" else ("#dc2626" if r["outcome"]=="incorrect" else "#6b7280")
                icon  = "✅" if r["outcome"]=="correct" else ("❌" if r["outcome"]=="incorrect" else "—")
                st.markdown(
                    f'{icon} **{r["date"]}** | Recommended: **{r["action"]}** | '
                    f'P&L then: {r["pnl_at_recommendation"]:+.1f}% → now: {r["pnl_next_run"]:+.1f}% | '
                    f'<span style="color:{color};font-weight:700">Change: {chg:+.1f}%</span> | '
                    f'Regime: {r["regime"]}',
                    unsafe_allow_html=True,
                )

    st.divider()

    # What-if: cumulative impact of following all recommendations
    st.subheader("What-If: P&L Impact of Following Recommendations")
    st.caption("Sum of P&L changes for positions where action was HOLD/ADD vs EXIT.")

    hold_gains  = sum(r["pnl_change"] for r in rows if r["action"] in ("HOLD","HOLD_WATCH","ADD"))
    exit_saves  = sum(-r["pnl_change"] for r in rows if r["action"]=="EXIT" and r["pnl_change"] < 0)
    wrong_holds = sum(r["pnl_change"] for r in rows if r["action"] in ("HOLD","HOLD_WATCH") and r["pnl_change"] < 0)

    c1,c2,c3 = st.columns(3)
    c1.metric("Cumulative P&L from HOLD/ADD calls", f"{hold_gains:+.1f}%")
    c2.metric("Losses avoided by correct EXIT",     f"{exit_saves:+.1f}%")
    c3.metric("P&L lost from wrong HOLD calls",     f"{wrong_holds:+.1f}%")

    st.divider()

    # Regime breakdown
    st.subheader("Accuracy by Macro Regime")
    regimes_seen = list(dict.fromkeys(r["regime"] for r in rows))
    for reg in regimes_seen:
        reg_rows  = [r for r in rows if r["regime"] == reg]
        reg_corr  = sum(1 for r in reg_rows if r["outcome"] == "correct")
        reg_acc   = reg_corr / len(reg_rows) * 100 if reg_rows else 0
        st.markdown(f"**{reg}** — {reg_acc:.0f}% accuracy ({reg_corr}/{len(reg_rows)} correct calls)")

    # History list
    st.divider()
    st.subheader("Report History")
    st.caption("All past portfolio runs available for review.")
    for rep in reports:
        ts  = rep["timestamp"][:19].replace("T"," ")
        adv = rep["data"].get("advisor",{})
        actions_summary = ", ".join(
            f"{a.get('ticker','?')}:{a.get('confirmed_action',a.get('action','?'))}"
            for a in adv.get("holdings_actions",[])
        )
        regime_rep = rep["data"].get("macro_chain",{}).get("market_regime","?").upper()
        with st.expander(f"**{ts}**  ·  {regime_rep}  ·  {actions_summary}", expanded=False):
            st.json(rep["data"])


# ── Main layout ──────────────────────────────────────────────────────────────────

st.title("📈 HMAS Investment Dashboard")

main_portfolio, main_scout, main_simulation = st.tabs([
    "📋 Portfolio",
    "🔍 Scout",
    "🎮 Simulation",
])

# ── Portfolio tab ────────────────────────────────────────────────────────────────
with main_portfolio:
    render_run_controls("portfolio", "portfolio", "Portfolio Analysis")
    st.divider()

    report_p = load_report("portfolio")
    if report_p is None:
        st.warning("No portfolio analysis found yet. Click **▶ Run Portfolio Analysis** above.")
    else:
        render_portfolio(report_p)

    # History
    hist_p = list_reports("portfolio", limit=15)
    if hist_p:
        st.markdown("---")
        with st.expander(f"📂 Report History ({len(hist_p)} runs)", expanded=False):
            for rep in hist_p:
                ts  = rep["timestamp"][:19].replace("T"," ")
                adv = rep["data"].get("advisor",{})
                regime_rep = rep["data"].get("macro_chain",{}).get("market_regime","?").upper()
                actions_sum = " | ".join(
                    f"{a.get('ticker','?')}:{a.get('confirmed_action',a.get('action','?'))}"
                    for a in adv.get("holdings_actions",[])
                )
                st.markdown(f"**{ts}**  ·  {regime_rep}  ·  {actions_sum}")


# ── Scout tab ────────────────────────────────────────────────────────────────────
with main_scout:
    render_run_controls("scout", "scout", "Scout Analysis")
    st.divider()

    report_s = load_report("scout")
    if report_s is None:
        st.warning("No scout analysis found yet. Click **▶ Run Scout Analysis** above.")
    else:
        render_scout(report_s)

    # History
    hist_s = list_reports("scout", limit=15)
    if hist_s:
        st.markdown("---")
        with st.expander(f"📂 Scout History ({len(hist_s)} runs)", expanded=False):
            for rep in hist_s:
                ts  = rep["timestamp"][:19].replace("T"," ")
                sel = rep["data"].get("selection",{})
                regime_rep = rep["data"].get("macro_chain",{}).get("market_regime","?").upper()
                top5_sum = ", ".join(t.get("ticker","?") for t in sel.get("top5",[]))
                st.markdown(f"**{ts}**  ·  {regime_rep}  ·  Top 5: {top5_sum}")


# ── Simulation tab ───────────────────────────────────────────────────────────────
with main_simulation:
    render_simulation()
