"""
ScoutHistory — log of which tickers were selected in each scout run.

Used by SelectionAgent to give a priority boost to tickers that appeared
in the last 7 days — if a strong setup was identified last week, it likely
still deserves attention. Don't lose the thread.

Format:
{
  "runs": [
    {
      "date": "2025-03-27",
      "timestamp": "2025-03-27T10:45:00",
      "top5": ["INFY.NS", "TCS.NS", "GOLDBEES.NS", "SUNPHARMA.NS", "LTIM.NS"],
      "regime": "risk-off"
    },
    ...
  ]
}
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Set

_PATH = Path(__file__).parent.parent.parent / "data" / "scout_history.json"
_KEEP_RUNS = 30   # Keep last 30 runs (≈ 30 weeks of weekly runs)
_PRIORITY_WINDOW_DAYS = 7


class ScoutHistory:
    """Persistent log of scout selections with priority-boost lookback."""

    def __init__(self):
        self._data = self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def tickers_in_window(self, days: int = _PRIORITY_WINDOW_DAYS) -> Set[str]:
        """
        Return the set of tickers selected in any scout run within the last `days` days.
        These get a score boost in the current SelectionAgent run.
        """
        cutoff = datetime.now() - timedelta(days=days)
        result: Set[str] = set()
        for run in self._data.get("runs", []):
            try:
                run_date = datetime.fromisoformat(run["timestamp"])
            except Exception:
                try:
                    run_date = datetime.strptime(run["date"], "%Y-%m-%d")
                except Exception:
                    continue
            if run_date >= cutoff:
                result.update(run.get("top5", []))
        return result

    def record_run(self, top5: List[str], regime: str = "unknown") -> None:
        """Record the result of a scout run."""
        runs = self._data.get("runs", [])
        runs.insert(0, {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "top5": top5,
            "regime": regime,
        })
        # Keep only the last N runs
        self._data["runs"] = runs[:_KEEP_RUNS]
        self._save()

    def recent_runs_summary(self, n: int = 4) -> str:
        """Return a formatted string of the last n runs for display."""
        runs = self._data.get("runs", [])[:n]
        if not runs:
            return "No prior scout runs."
        lines = []
        for r in runs:
            tickers = ", ".join(r.get("top5", []))
            lines.append(f"  [{r['date']}] {r.get('regime','?')} → {tickers}")
        return "\n".join(lines)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        if not _PATH.exists():
            return {"runs": []}
        try:
            with open(_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"runs": []}

    def _save(self) -> None:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
