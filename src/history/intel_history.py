"""
IntelHistory — rolling history for the 4 Phase-0 intelligence agents.

Each agent keeps its own JSON file. On every run:
  1. Load previous entries
  2. Agent runs and produces today's analysis
  3. Append new entry, prune old ones beyond the window
  4. Recompute trend_summary from recent entries
  5. Save back to file

The trend_summary is what gets injected into the agent's prompt so it
can reason "this has been happening for 3 weeks" not just "this happened today".
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "intel_history"


class IntelHistory:
    """
    Rolling history store for one intelligence agent.

    Args:
        agent_name: e.g. "news_intel", "global_markets", "geopolitics", "macro_data"
        window_days: How many days of history to keep (older entries are pruned)
    """

    def __init__(self, agent_name: str, window_days: int = 30):
        self.agent_name = agent_name
        self.window_days = window_days
        self._path = _DATA_DIR / f"{agent_name}.json"
        self._data: Dict[str, Any] = self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def entries(self) -> List[Dict[str, Any]]:
        return self._data.get("entries", [])

    @property
    def trend_summary(self) -> str:
        return self._data.get("trend_summary", "No prior history available — first run.")

    def append(
        self,
        summary: str,
        key_signals: List[str],
        regime: str = "unknown",
        extra: Optional[Dict] = None,
    ) -> None:
        """
        Append today's analysis entry and prune stale ones.

        Args:
            summary:     One-paragraph plain-English summary of today's reading
            key_signals: Bullet list of the most important signals (max 5)
            regime:      e.g. "risk-off", "risk-on", "mixed"
            extra:       Any additional agent-specific fields to store
        """
        entry: Dict[str, Any] = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "key_signals": key_signals[:5],
            "regime": regime,
        }
        if extra:
            entry.update(extra)

        entries = self._data.get("entries", [])
        entries.insert(0, entry)  # newest first
        entries = self._prune(entries)
        self._data["entries"] = entries
        self._data["trend_summary"] = self._compute_trend(entries)
        self._data["agent"] = self.agent_name
        self._data["last_updated"] = datetime.now().isoformat()
        self._save()

    def context_for_prompt(self, max_entries: int = 7) -> str:
        """
        Return a formatted string suitable for injecting into an LLM prompt.
        Includes the trend summary + last N individual entries.
        """
        lines = [
            f"## {self.agent_name.replace('_', ' ').title()} — Historical Context",
            f"**Multi-week trend:** {self.trend_summary}",
            "",
        ]
        recent = self.entries[:max_entries]
        if recent:
            lines.append("**Recent entries (newest first):**")
            for e in recent:
                lines.append(f"  [{e['date']}] regime={e.get('regime','?')}  {e['summary'][:200]}")
                sigs = e.get("key_signals", [])
                if sigs:
                    lines.append("    Key signals: " + " | ".join(sigs[:3]))
        else:
            lines.append("No prior entries.")
        return "\n".join(lines)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _prune(self, entries: List[Dict]) -> List[Dict]:
        """Remove entries older than window_days."""
        cutoff = datetime.now() - timedelta(days=self.window_days)
        return [
            e for e in entries
            if datetime.strptime(e["date"], "%Y-%m-%d") >= cutoff
        ]

    def _compute_trend(self, entries: List[Dict]) -> str:
        """Build a human-readable trend sentence from recent entries."""
        if not entries:
            return "No history available."
        if len(entries) == 1:
            return f"First reading: {entries[0]['regime']} regime. {entries[0]['summary'][:100]}"

        # Look at the last 4 entries for regime consistency
        recent = entries[:4]
        regimes = [e.get("regime", "unknown") for e in recent]
        regime_counts: Dict[str, int] = {}
        for r in regimes:
            regime_counts[r] = regime_counts.get(r, 0) + 1

        dominant_regime = max(regime_counts, key=lambda k: regime_counts[k])
        streak = regime_counts[dominant_regime]

        # Collect key signals across recent entries (deduplicated)
        seen: set = set()
        all_signals: List[str] = []
        for e in recent:
            for sig in e.get("key_signals", []):
                key = sig[:40].lower()
                if key not in seen:
                    seen.add(key)
                    all_signals.append(sig)

        trend = (
            f"{dominant_regime.upper()} regime for {streak} of last {len(recent)} readings. "
            f"Persistent signals: {'; '.join(all_signals[:3]) if all_signals else 'None identified'}."
        )
        return trend

    def _load(self) -> Dict[str, Any]:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            return {"agent": self.agent_name, "entries": [], "trend_summary": "No prior history."}
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"agent": self.agent_name, "entries": [], "trend_summary": "History file corrupted — reset."}

    def _save(self) -> None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
