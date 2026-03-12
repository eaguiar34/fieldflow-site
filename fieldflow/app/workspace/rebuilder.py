from __future__ import annotations

"""
Event replay + projection driver.

This module is deliberately "infra-ish" and does NOT touch CPM logic.

It reads the merged append-only event stream (events/events.jsonl) and applies
events incrementally into a local workspace cache folder:

  workspace_root/
    events/events.jsonl              (shared merged stream)
    cache/
      replay_cursor.json             (where we left off)
      projections/
        controls_work_packages.json  (example materialized view)
        ...

The goal is to make sync meaningful:
  merge outboxes -> replay new events -> refresh UI from projections
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from fieldflow.app.workspace.event_log import Event


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class ReplayCursor:
    # Line number in events.jsonl (1-based lines read)
    line: int = 0
    updated_utc: str = ""


@dataclass
class ReplayStats:
    read_lines: int = 0
    applied_events: int = 0
    skipped_events: int = 0


class WorkspaceRebuilder:
    def __init__(self, workspace_root: Path) -> None:
        self.root = Path(workspace_root)
        self.events_path = self.root / "events" / "events.jsonl"

        self.cache_dir = self.root / "cache"
        self.projections_dir = self.cache_dir / "projections"
        self.cursor_path = self.cache_dir / "replay_cursor.json"

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.projections_dir.mkdir(parents=True, exist_ok=True)

        self._handlers: List[Callable[[Event], None]] = []

    def register_handler(self, fn: Callable[[Event], None]) -> None:
        self._handlers.append(fn)

    def load_cursor(self) -> ReplayCursor:
        if not self.cursor_path.exists():
            return ReplayCursor(line=0, updated_utc="")
        try:
            d = json.loads(self.cursor_path.read_text(encoding="utf-8"))
            return ReplayCursor(line=int(d.get("line", 0)), updated_utc=str(d.get("updated_utc", "")))
        except Exception:
            return ReplayCursor(line=0, updated_utc="")

    def save_cursor(self, cur: ReplayCursor) -> None:
        payload = {"line": int(cur.line), "updated_utc": cur.updated_utc or _now_iso()}
        self.cursor_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def replay_incremental(self, *, max_lines: int = 50000) -> ReplayStats:
        """
        Read merged events.jsonl incrementally from the last cursor line.

        Calls all registered handlers for each parsed Event.

        NOTE: We do not attempt to "interpret" conflicts here. We just replay.
        Conflict rules belong inside the projection handlers (latest-wins, etc.).
        """
        stats = ReplayStats()
        cursor = self.load_cursor()

        if not self.events_path.exists():
            return stats

        line_no = 0
        applied = 0
        skipped = 0

        with self.events_path.open("r", encoding="utf-8") as f:
            for line in f:
                line_no += 1
                if line_no <= cursor.line:
                    continue
                if stats.read_lines >= max_lines:
                    break

                stats.read_lines += 1
                s = line.strip()
                if not s:
                    skipped += 1
                    continue

                try:
                    d = json.loads(s)
                    e = Event(
                        ts_utc=str(d.get("ts_utc", "")),
                        actor=str(d.get("actor", "")),
                        entity=str(d.get("entity", "")),
                        entity_id=str(d.get("entity_id", "")),
                        op=str(d.get("op", "")),
                        payload=dict(d.get("payload", {}) or {}),
                    )
                except Exception:
                    skipped += 1
                    continue

                ok = False
                for h in self._handlers:
                    try:
                        h(e)
                        ok = True
                    except Exception:
                        # handler bugs should not kill the stream
                        continue

                if ok:
                    applied += 1
                else:
                    skipped += 1

        cursor.line = line_no
        cursor.updated_utc = _now_iso()
        self.save_cursor(cursor)

        stats.applied_events = applied
        stats.skipped_events = skipped
        return stats