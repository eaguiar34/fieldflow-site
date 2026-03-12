from __future__ import annotations

"""Shared-folder event sync (v1).

Goal: make collaboration possible on Windows domain shared drives and synced
folders (OneDrive/SharePoint) without a server.

Design choice:
  - Avoid concurrent writes to a single file on flaky network shares.
  - Each actor appends to their own outbox file: events/outbox/<actor>.jsonl
  - A merge step produces events/events.jsonl (read-optimized) and a cursor file
    per actor, so subsequent merges are incremental.

This is NOT full CRDT/OT magic. Conflict resolution is "log everything" +
"latest wins" when you later build state from events.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from fieldflow.app.workspace.event_log import Event


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_actor(name: str) -> str:
    s = (name or "unknown").strip()
    keep = [c for c in s if c.isalnum() or c in ("-", "_", ".")]
    out = "".join(keep) or "unknown"
    return out[:64]


def _event_fingerprint(e: Event) -> str:
    payload = json.dumps(e.payload or {}, sort_keys=True, ensure_ascii=False)
    return f"{e.ts_utc}|{e.actor}|{e.entity}|{e.entity_id}|{e.op}|{payload}"


@dataclass
class SyncStats:
    merged_events: int = 0
    new_outbox_events: int = 0
    actors_scanned: int = 0


class SharedFolderEventSync:
    def __init__(self, events_dir: Path, *, actor: str) -> None:
        self.events_dir = Path(events_dir)
        self.actor = _safe_actor(actor)

        self.outbox_dir = self.events_dir / "outbox"
        self.cursor_dir = self.events_dir / "cursors"
        self.merged_path = self.events_dir / "events.jsonl"
        self.self_outbox_path = self.outbox_dir / f"{self.actor}.jsonl"

    # ---------------- writing ----------------
    def append_local(self, *, entity: str, entity_id: str, op: str, payload: Dict) -> None:
        """Append to the actor's outbox (safe for shared folders)."""
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        e = Event(
            ts_utc=_now_iso(),
            actor=self.actor,
            entity=str(entity or ""),
            entity_id=str(entity_id or ""),
            op=str(op or ""),
            payload=dict(payload or {}),
        )
        line = json.dumps(e.__dict__, ensure_ascii=False)
        with self.self_outbox_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ---------------- merging ----------------
    def _load_cursor(self, actor: str) -> int:
        p = self.cursor_dir / f"{actor}.json"
        if not p.exists():
            return 0
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return int(d.get("line", 0))
        except Exception:
            return 0

    def _save_cursor(self, actor: str, line_no: int) -> None:
        self.cursor_dir.mkdir(parents=True, exist_ok=True)
        p = self.cursor_dir / f"{actor}.json"
        p.write_text(json.dumps({"line": int(line_no), "updated_utc": _now_iso()}, indent=2), encoding="utf-8")

    def merge(self, *, max_lines_per_actor: int = 25000) -> SyncStats:
        """Merge all actor outboxes into merged events.jsonl.

        Idempotent: we dedupe by a fingerprint string.
        Incremental: uses per-actor cursor line numbers.
        """
        stats = SyncStats()
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

        # Load existing fingerprints from merged file (bounded for safety).
        seen: set[str] = set()
        if self.merged_path.exists():
            try:
                with self.merged_path.open("r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if i >= 50000:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            e = Event(
                                ts_utc=str(d.get("ts_utc", "")),
                                actor=str(d.get("actor", "")),
                                entity=str(d.get("entity", "")),
                                entity_id=str(d.get("entity_id", "")),
                                op=str(d.get("op", "")),
                                payload=dict(d.get("payload", {}) or {}),
                            )
                            seen.add(_event_fingerprint(e))
                        except Exception:
                            continue
            except Exception:
                pass

        out_lines: List[str] = []

        for p in sorted(self.outbox_dir.glob("*.jsonl")):
            actor = p.stem
            stats.actors_scanned += 1
            start = self._load_cursor(actor)
            line_no = 0
            new_count = 0

            try:
                with p.open("r", encoding="utf-8") as f:
                    for line in f:
                        line_no += 1
                        if line_no <= start:
                            continue
                        if new_count >= max_lines_per_actor:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            e = Event(
                                ts_utc=str(d.get("ts_utc", "")),
                                actor=str(d.get("actor", "")),
                                entity=str(d.get("entity", "")),
                                entity_id=str(d.get("entity_id", "")),
                                op=str(d.get("op", "")),
                                payload=dict(d.get("payload", {}) or {}),
                            )
                            fp = _event_fingerprint(e)
                            if fp in seen:
                                continue
                            seen.add(fp)
                            out_lines.append(json.dumps(e.__dict__, ensure_ascii=False))
                            new_count += 1
                        except Exception:
                            continue
            except Exception:
                continue

            if new_count > 0:
                self._save_cursor(actor, start + new_count)
                stats.merged_events += new_count

        if out_lines:
            with self.merged_path.open("a", encoding="utf-8") as f:
                for line in out_lines:
                    f.write(line + "\n")

        return stats