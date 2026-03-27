"""
report_history.py — Per-mode JSON report archive and previous-context loader.

Responsibilities:
  - Save each run as reports/portfolio/YYYY-MM-DD_HHMMSS.json
                    or reports/scout/YYYY-MM-DD_HHMMSS.json
  - Maintain a .last_report_{mode}.json shortcut for instant dashboard load
  - Load the N most recent reports for a given mode
  - Produce a compact "previous context" string that agents inject into prompts
    so each run learns from the last one without re-querying LLMs

Usage (from run.py or workflow):
    from src.core.report_history import ReportHistory
    rh = ReportHistory()
    rh.save("portfolio", result_dict)
    ctx = rh.get_previous_context("portfolio")   # → str or ""
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


_ROOT = Path(__file__).parent.parent.parent   # project root
_REPORTS_DIR = _ROOT / "reports"


class ReportHistory:

    def __init__(self, reports_dir: Path = _REPORTS_DIR):
        self.base = reports_dir
        self._ensure_dirs()

    # ── Public API ─────────────────────────────────────────────────────────────

    def save(self, mode: str, result: Dict[str, Any]) -> Path:
        """
        Persist *result* as a JSON file in reports/{mode}/.
        Also writes .last_report_{mode}.json at project root.

        mode: "portfolio" or "scout"
        """
        folder = self._mode_dir(mode)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = folder / f"{ts}.json"
        _write_json(path, result)

        # Update the "latest" shortcut
        latest = _ROOT / f".last_report_{mode}.json"
        _write_json(latest, result)

        return path

    def load_latest(self, mode: str) -> Optional[Dict[str, Any]]:
        """Return the most recent report for *mode*, or None."""
        # Prefer the quick-access shortcut
        shortcut = _ROOT / f".last_report_{mode}.json"
        if shortcut.exists():
            try:
                return json.loads(shortcut.read_text(encoding="utf-8"))
            except Exception:
                pass
        # Fall back to newest file in folder
        files = sorted(self._mode_dir(mode).glob("*.json"), reverse=True)
        if not files:
            return None
        try:
            return json.loads(files[0].read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_reports(self, mode: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Return metadata (timestamp, path, elapsed_seconds, brief summary)
        for the most recent *limit* reports for *mode*.
        """
        files = sorted(self._mode_dir(mode).glob("*.json"), reverse=True)[:limit]
        results = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append({
                    "file":     str(f),
                    "filename": f.stem,
                    "timestamp": data.get("timestamp", f.stem),
                    "elapsed_seconds": data.get("elapsed_seconds", 0),
                    "summary": _brief_summary(mode, data),
                    "data": data,
                })
            except Exception:
                continue
        return results

    def get_previous_context(self, mode: str) -> str:
        """
        Return a compact previous-session context string for injection into
        agent prompts.  Returns "" if no history exists yet.
        """
        reports = self.list_reports(mode, limit=2)
        if not reports:
            return ""
        prev = reports[0]["data"] if len(reports) >= 1 else None
        if prev is None:
            return ""
        if mode == "portfolio":
            return _portfolio_context_string(prev)
        elif mode == "scout":
            return _scout_context_string(prev)
        return ""

    # ── Internal ───────────────────────────────────────────────────────────────

    def _mode_dir(self, mode: str) -> Path:
        d = self.base / mode
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _ensure_dirs(self):
        for m in ("portfolio", "scout"):
            (self.base / m).mkdir(parents=True, exist_ok=True)


# ── Context formatters ─────────────────────────────────────────────────────────

def _portfolio_context_string(report: Dict[str, Any]) -> str:
    """Compact previous-portfolio-run summary for agent prompt injection."""
    ts = report.get("timestamp", "")[:10]
    macro = report.get("macro_chain", {})
    prev_regime = macro.get("market_regime", "unknown").upper()
    prev_causal = macro.get("causal_chain", "")[:200]

    advisor = report.get("advisor", {})
    adv_actions = advisor.get("holdings_actions", [])

    lines = [
        f"=== PREVIOUS PORTFOLIO RUN ({ts}) ===",
        f"Macro regime then: {prev_regime}",
        f"Causal chain then: {prev_causal}",
        "",
        "Previous recommended actions per holding:",
    ]
    for a in adv_actions:
        ticker = a.get("ticker", "?")
        action = a.get("confirmed_action") or a.get("action", "?")
        pnl    = a.get("pnl_pct", "?")
        bst    = a.get("blank_slate_test", "?")
        lines.append(
            f"  {ticker}: {action}  |  P&L at time: {pnl:+.1f}%  |  blank-slate: {bst}"
            if isinstance(pnl, (int, float)) else
            f"  {ticker}: {action}  |  blank-slate: {bst}"
        )

    checklist = advisor.get("next_30_days_checklist", [])
    if checklist:
        lines.append("")
        lines.append("Previous 30-day checklist items set:")
        for item in checklist[:3]:
            lines.append(f"  - {item[:120]}")

    lines.append("=== END PREVIOUS RUN ===")
    return "\n".join(lines)


def _scout_context_string(report: Dict[str, Any]) -> str:
    """Compact previous-scout-run summary for agent prompt injection."""
    ts = report.get("timestamp", "")[:10]
    macro = report.get("macro_chain", {})
    prev_regime = macro.get("market_regime", "unknown").upper()

    selection = report.get("selection", {})
    top5 = selection.get("top5", [])

    lines = [
        f"=== PREVIOUS SCOUT RUN ({ts}) ===",
        f"Macro regime then: {prev_regime}",
        "Previous top-5 picks:",
    ]
    for item in top5:
        ticker = item.get("ticker", "?")
        rec    = item.get("recommendation", "?")
        score  = item.get("final_score", "?")
        conv   = item.get("conviction", "?")
        lines.append(f"  {ticker}: {rec}  score={score}  conviction={conv}")

    lines.append("=== END PREVIOUS RUN ===")
    return "\n".join(lines)


def _brief_summary(mode: str, data: Dict[str, Any]) -> str:
    if mode == "portfolio":
        advisor = data.get("advisor", {})
        actions = advisor.get("holdings_actions", [])
        action_str = ", ".join(
            f"{a.get('ticker','?')}:{a.get('confirmed_action','?')}"
            for a in actions
        )
        regime = data.get("macro_chain", {}).get("market_regime", "?").upper()
        return f"Regime: {regime} | {action_str}"
    elif mode == "scout":
        top5 = data.get("selection", {}).get("top5", [])
        tickers = [t.get("ticker", "?") for t in top5]
        regime = data.get("macro_chain", {}).get("market_regime", "?").upper()
        return f"Regime: {regime} | Top 5: {', '.join(tickers)}"
    return ""


# ── Utility ────────────────────────────────────────────────────────────────────

def _write_json(path: Path, data: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
