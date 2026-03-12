from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

from fieldflow.app.controls_models import Submittal
from fieldflow.domain.scheduling.calendar import WorkCalendar


@dataclass(frozen=True)
class SubmittalFinding:
    severity: str  # INFO/WARN/FAIL
    submittal_id: str
    message: str


def check_submittals(
    *,
    submittals: List[Submittal],
    activity_start_by_id: Dict[str, date],
    calendar: WorkCalendar,
    today: Optional[date] = None,
) -> List[SubmittalFinding]:
    """Basic checker.

    Rules (simple/pro):
      - If required_by activity has ES date:
          - If status != Approved and ES is within lead_time_days (working) from today -> WARN
          - If approve_date exists and approve_date > ES -> FAIL
          - If status is Approved but approve_date missing -> WARN
      - If required_by missing -> WARN
    """

    if today is None:
        today = date.today()

    findings: List[SubmittalFinding] = []

    def add_workdays(start: date, n: int) -> date:
        # use calendar math: add_working_days counts from start inclusive? In your calendar, it adds N workdays forward.
        return calendar.add_working_days(start, n)

    for s in submittals:
        if not s.required_by_activity_id:
            findings.append(SubmittalFinding("WARN", s.id, "Missing required-by activity."))
            continue

        es = activity_start_by_id.get(s.required_by_activity_id)
        if es is None:
            findings.append(SubmittalFinding("WARN", s.id, f"Required-by activity '{s.required_by_activity_id}' not found in schedule."))
            continue

        if s.status.lower() == "approved" and s.approve_date is None:
            findings.append(SubmittalFinding("WARN", s.id, "Status Approved but approve_date is blank."))

        if s.approve_date is not None and s.approve_date > es:
            findings.append(SubmittalFinding("FAIL", s.id, f"Approved on {s.approve_date} AFTER activity start {es}."))

        # lead time proximity warning
        if s.status.lower() != "approved":
            # deadline = today + lead_time_days working
            deadline = add_workdays(today, max(0, int(s.lead_time_days)))
            if es <= deadline:
                findings.append(SubmittalFinding("WARN", s.id, f"Activity starts {es}; not approved; within lead time window (lead={s.lead_time_days} wd)."))

    # If no issues, show an info
    if not findings and submittals:
        findings.append(SubmittalFinding("INFO", "", "No submittal issues detected."))

    return findings
