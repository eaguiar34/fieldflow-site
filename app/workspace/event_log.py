from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclass
class Event:
    ts_utc: str
    actor: str
    entity: str
    entity_id: str
    op: str
    payload: Dict


class EventLog:
    """
    Append-only JSONL event log.

    Stored at: workspace/events/events.jsonl

    This is a stepping stone to full sync later.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, e: Event) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(e.__dict__, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def append_simple(self, actor: str, entity: str, entity_id: str, op: str, payload: Dict) -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        self.append(Event(ts_utc=ts, actor=actor, entity=entity, entity_id=entity_id, op=op, payload=payload))

    def read_all(self, limit: int = 2000) -> List[Event]:
        if not self.path.exists():
            return []
        out: List[Event] = []
        with self.path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    out.append(Event(
                        ts_utc=str(d.get("ts_utc", "")),
                        actor=str(d.get("actor", "")),
                        entity=str(d.get("entity", "")),
                        entity_id=str(d.get("entity_id", "")),
                        op=str(d.get("op", "")),
                        payload=dict(d.get("payload", {}) or {}),
                    ))
                except Exception:
                    continue
        return out