from __future__ import annotations

"""Controls impacts and provenance.

This module is used to translate project-controls artifacts (RFIs/Submittals)
into *schedule impacts* applied to a scenario derived from Baseline.

Design goals:
- Offline-first (no external deps)
- Conservative scheduling semantics (only push later / increase durations)
- UI-friendly provenance: given an activity id, explain which controls affect it

Impact rules (simple and transparent):

1) RFIs
   - If status is Open or Pending and impact_days > 0
   - For each linked activity id, increase duration_days by impact_days.
   - Multiple RFIs accumulate.

2) Submittals
   - If status is not Approved and lead_time_days > 0
   - The required activity cannot start until:
       ready = (submit_date if present else today) + lead_time_days (working days)
   - Implemented as an SNET constraint; if an SNET exists, we keep the later date.

This is intentionally straightforward and extensible.
"""

from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from fieldflow.app.controls_models import RFI, Submittal
from fieldflow.app.scenarios import ScenarioState
from fieldflow.domain.scheduling.calendar import WorkCalendar
from fieldflow.domain.scheduling.types import Activity


def controls_provenance_for_activity(
    *,
    rfis: Iterable[RFI],
    submittals: Iterable[Submittal],
    activity_id: str,
    today: date,
) -> List[str]:
    """Return human-readable reasons a given activity is impacted by controls."""
    aid = (activity_id or "").strip()
    if not aid:
        return []

    out: List[str] = []

    def _split_ids(csv: str) -> List[str]:
        return [x.strip() for x in (csv or "").split(",") if x.strip()]

    # RFIs
    for rfi in rfis:
        status_raw = (getattr(rfi, "status", "") or "").strip()
        status = status_raw.lower()
        if status not in ("open", "pending"):
            continue
        impact = int(getattr(rfi, "impact_days", 0) or 0)
        if impact <= 0:
            continue
        ids = _split_ids(getattr(rfi, "linked_activity_ids", ""))
        if aid not in ids:
            continue
        title = (getattr(rfi, "title", "") or "").strip()
        label = f"RFI {getattr(rfi, 'id', '?')} ({status_raw}) +{impact}d"
        if title:
            label += f": {title}"
        out.append(label)

    # Submittals
    for sub in submittals:
        status_raw = (getattr(sub, "status", "") or "").strip()
        status = status_raw.lower()
        if status == "approved":
            continue
        lead = int(getattr(sub, "lead_time_days", 0) or 0)
        if lead <= 0:
            continue
        req = (getattr(sub, "required_by_activity_id", "") or "").strip()
        if req != aid:
            continue
        submit_dt = getattr(sub, "submit_date", None) or today
        name = (getattr(sub, "name", "") or "").strip()
        label = (
            f"Submittal {getattr(sub, 'id', '?')} ({status_raw}) lead {lead}d, "
            f"submit {submit_dt}"
        )
        if name:
            label += f": {name}"
        out.append(label)

    return out


def controls_provenance_entries_for_activity(
    *,
    rfis: Iterable[RFI],
    submittals: Iterable[Submittal],
    activity_id: str,
    today: date,
) -> List[dict]:
    """Return structured provenance entries for an activity.

    Each entry is a dict:
      {
        "page": "rfis" | "submittals",
        "select_id": <control id>,
        "label": <human readable text>
      }

    UI can use this to render clickable "deep links".
    """
    aid = (activity_id or "").strip()
    if not aid:
        return []

    out: List[dict] = []

    def _split_ids(csv: str) -> List[str]:
        return [x.strip() for x in (csv or "").split(",") if x.strip()]

    for rfi in rfis:
        status_raw = (getattr(rfi, "status", "") or "").strip()
        status = status_raw.lower()
        if status not in ("open", "pending"):
            continue
        impact = int(getattr(rfi, "impact_days", 0) or 0)
        if impact <= 0:
            continue
        ids = _split_ids(getattr(rfi, "linked_activity_ids", ""))
        if aid not in ids:
            continue
        title = (getattr(rfi, "title", "") or "").strip()
        rid = str(getattr(rfi, "id", "?"))
        label = f"RFI {rid} ({status_raw}) +{impact}d"
        if title:
            label += f": {title}"
        out.append({"page": "rfis", "select_id": rid, "label": label})

    for sub in submittals:
        status_raw = (getattr(sub, "status", "") or "").strip()
        status = status_raw.lower()
        if status == "approved":
            continue
        lead = int(getattr(sub, "lead_time_days", 0) or 0)
        if lead <= 0:
            continue
        req = (getattr(sub, "required_by_activity_id", "") or "").strip()
        if req != aid:
            continue
        submit_dt = getattr(sub, "submit_date", None) or today
        sid = str(getattr(sub, "id", "?"))
        name = (getattr(sub, "name", "") or "").strip()
        label = f"Submittal {sid} ({status_raw}) lead {lead}d, submit {submit_dt}"
        if name:
            label += f": {name}"
        out.append({"page": "submittals", "select_id": sid, "label": label})

    return out


def build_controls_impact_scenario(
    *,
    baseline: ScenarioState,
    rfis: Iterable[RFI],
    submittals: Iterable[Submittal],
    calendar: WorkCalendar,
    today: date,
) -> Tuple[ScenarioState, List[str]]:
    """Backward-compatible builder: returns (scenario_state, warnings)."""
    scenario, warnings, _prov = build_controls_impact_scenario_with_provenance(
        baseline=baseline,
        rfis=rfis,
        submittals=submittals,
        calendar=calendar,
        today=today,
    )
    return scenario, warnings


def build_controls_impact_scenario_with_provenance(
    *,
    baseline: ScenarioState,
    rfis: Iterable[RFI],
    submittals: Iterable[Submittal],
    calendar: WorkCalendar,
    today: date,
) -> Tuple[ScenarioState, List[str], Dict[str, List[str]]]:
    """Return (scenario_state, warnings, provenance_by_activity_id)."""
    warnings: List[str] = []

    # Copy activities and index by id
    acts: List[Activity] = [
        Activity(a.id, a.name, int(a.duration_days), snet=a.snet, fnet=a.fnet) for a in baseline.activities
    ]
    by_id: Dict[str, Activity] = {a.id: a for a in acts}

    def _split_ids(csv: str) -> List[str]:
        return [x.strip() for x in (csv or "").split(",") if x.strip()]

    prov: Dict[str, List[str]] = {}

    # --- RFI impacts: duration bumps ---
    dur_bumps: Dict[str, int] = {}
    for rfi in rfis:
        status_raw = (getattr(rfi, "status", "") or "").strip()
        status = status_raw.lower()
        if status not in ("open", "pending"):
            continue
        impact = int(getattr(rfi, "impact_days", 0) or 0)
        if impact <= 0:
            continue
        ids = _split_ids(getattr(rfi, "linked_activity_ids", ""))
        if not ids:
            continue
        title = (getattr(rfi, "title", "") or "").strip()
        for aid in ids:
            if aid not in by_id:
                warnings.append(f"RFI {getattr(rfi, 'id', '?')}: linked activity '{aid}' not found")
                continue
            dur_bumps[aid] = dur_bumps.get(aid, 0) + impact
            msg = f"RFI {getattr(rfi, 'id', '?')} ({status_raw}) +{impact}d"
            if title:
                msg += f": {title}"
            prov.setdefault(aid, []).append(msg)

    for aid, bump in dur_bumps.items():
        a = by_id.get(aid)
        if a is None:
            continue
        new_dur = max(0, int(a.duration_days) + int(bump))
        by_id[aid] = Activity(a.id, a.name, new_dur, snet=a.snet, fnet=a.fnet)

    # --- Submittal impacts: SNET push ---
    for sub in submittals:
        status_raw = (getattr(sub, "status", "") or "").strip()
        status = status_raw.lower()
        if status == "approved":
            continue
        lead = int(getattr(sub, "lead_time_days", 0) or 0)
        if lead <= 0:
            continue

        req_id = (getattr(sub, "required_by_activity_id", "") or "").strip()
        if not req_id:
            warnings.append(f"Submittal {getattr(sub, 'id', '?')}: missing required_by_activity_id")
            continue
        a = by_id.get(req_id)
        if a is None:
            warnings.append(f"Submittal {getattr(sub, 'id', '?')}: required activity '{req_id}' not found")
            continue

        base_date = getattr(sub, "submit_date", None) or today
        try:
            ready = calendar.add_working_days(base_date, lead)
            ready = calendar.next_working_day(ready)
        except Exception:
            ready = calendar.next_working_day(base_date)

        name = (getattr(sub, "name", "") or "").strip()
        msg = (
            f"Submittal {getattr(sub, 'id', '?')} ({status_raw}) lead {lead}d, submit {base_date}"
        )
        if name:
            msg += f": {name}"
        prov.setdefault(req_id, []).append(msg)

        snet: Optional[date] = a.snet
        if snet is None or ready > snet:
            by_id[req_id] = Activity(a.id, a.name, int(a.duration_days), snet=ready, fnet=a.fnet)

    # Rebuild activity list preserving original ordering
    new_acts: List[Activity] = [by_id[a.id] for a in acts]

    out = ScenarioState(name=baseline.name, activities=new_acts, relationships=list(baseline.relationships))
    return out, warnings, prov
