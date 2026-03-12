from __future__ import annotations

"""Human-friendly reporting built on the append-only event log."""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

from fieldflow.app.workspace.event_log import Event


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


@dataclass
class ChangeSummary:
    title: str
    lines: List[str]


def changes_since(
    events: Iterable[Event],
    *,
    since_utc_iso: str,
    limit: int = 5000,
) -> ChangeSummary:
    """Create a concise 'changes since' summary."""

    since_dt = _parse_ts(since_utc_iso)
    if since_dt is None:
        return ChangeSummary(title="Changes", lines=[f"Invalid timestamp: {since_utc_iso}"])

    picked: List[Tuple[datetime, Event]] = []
    for e in events:
        dt = _parse_ts(e.ts_utc)
        if dt is None:
            continue
        if dt >= since_dt:
            picked.append((dt, e))
        if len(picked) >= limit:
            break

    picked.sort(key=lambda t: t[0])

    lines: List[str] = []
    last_key = None
    for dt, e in picked:
        key = (e.entity, e.entity_id)
        if key != last_key:
            lines.append("")
            lines.append(f"{e.entity}:{e.entity_id}")
            lines.append("-" * min(60, len(lines[-1])))
            last_key = key
        actor = e.actor or "unknown"
        op = e.op or "change"
        lines.append(f"{dt.isoformat(timespec='seconds')}  {actor}  {op}  {e.payload}")

    if not lines:
        lines = ["No events in this window."]

    title = f"Changes since {since_dt.isoformat(timespec='seconds')}"
    return ChangeSummary(title=title, lines=lines)