from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
import re
import xml.etree.ElementTree as ET

from fieldflow.domain.scheduling.types import Activity, Relationship, RelType


@dataclass(frozen=True)
class MSProjectImportResult:
    project_start: Optional[date]
    holidays: Set[date]
    activities: List[Activity]
    relationships: List[Relationship]
    warnings: List[str]


def import_msproject_xml(path: str | Path) -> MSProjectImportResult:
    """
    Import Microsoft Project MSPDI XML into FieldFlow domain objects.

    Supported:
      - Project start date (<StartDate>)
      - Tasks: ID/Name/Duration + ConstraintType mapping to SNET/FNET
      - Predecessor links: FS/SS/FF/SF + lag (converted to whole workdays)
      - Calendar exceptions -> holidays (FromDate..ToDate inclusive)

    Notes:
      - Skips Summary tasks
      - Milestones will often import as duration 0 (fine)
    """
    path = Path(path)
    xml_text = path.read_text(encoding="utf-8", errors="ignore")
    root = ET.fromstring(xml_text)

    _strip_namespaces(root)

    warnings: List[str] = []

    project_start = _parse_project_start(root, warnings)
    holidays = _parse_project_holidays(root, warnings)

    tasks_el = root.find("./Tasks") or root.find("./Project/Tasks")
    if tasks_el is None:
        warnings.append("No <Tasks> element found.")
        return MSProjectImportResult(project_start, holidays, [], [], warnings)

    uid_to_id: Dict[str, str] = {}

    activities: List[Activity] = []
    seen: Set[str] = set()

    # ---- Activities pass
    for task_el in tasks_el.findall("./Task"):
        if _text(task_el.find("./IsNull")) == "1":
            continue
        if _text(task_el.find("./Summary")) == "1":
            continue

        uid = _text(task_el.find("./UID"))
        task_id = _text(task_el.find("./ID")) or uid
        name = _text(task_el.find("./Name")) or task_id

        if not task_id:
            warnings.append("Skipped a task with no ID/UID.")
            continue
        if task_id in seen:
            warnings.append(f"Duplicate Task ID encountered: {task_id}. Keeping first occurrence.")
            continue
        seen.add(task_id)

        if uid:
            uid_to_id[uid] = task_id

        dur_text = _text(task_el.find("./Duration"))
        duration_days = _parse_duration_to_days(dur_text, warnings, context=f"Task {task_id}") if dur_text else 0

        constraint_type = _text(task_el.find("./ConstraintType"))
        constraint_date_txt = _text(task_el.find("./ConstraintDate"))
        snet: Optional[date] = None
        fnet: Optional[date] = None

        # MSPDI ConstraintType codes:
        # 4 = Start No Earlier Than (SNET)
        # 6 = Finish No Earlier Than (FNET)
        if constraint_type and constraint_date_txt:
            cdate = _parse_dt_to_date(constraint_date_txt, warnings, context=f"Task {task_id} ConstraintDate")
            if cdate:
                if constraint_type == "4":
                    snet = cdate
                elif constraint_type == "6":
                    fnet = cdate

        activities.append(
            Activity(
                id=str(task_id),
                name=name,
                duration_days=int(duration_days),
                snet=snet,
                fnet=fnet,
            )
        )

    # ---- Relationships pass
    relationships: List[Relationship] = []
    for task_el in tasks_el.findall("./Task"):
        if _text(task_el.find("./IsNull")) == "1":
            continue
        if _text(task_el.find("./Summary")) == "1":
            continue

        succ_uid = _text(task_el.find("./UID"))
        succ_id = _text(task_el.find("./ID")) or succ_uid
        if not succ_id:
            continue

        for pl in task_el.findall("./PredecessorLink"):
            pred_uid = _text(pl.find("./PredecessorUID"))
            pred_id = uid_to_id.get(pred_uid, pred_uid)

            if not pred_id:
                warnings.append(f"Task {succ_id}: predecessor link missing PredecessorUID.")
                continue

            type_code = _text(pl.find("./Type")) or "1"  # default FS
            rel_type = _map_link_type(type_code, warnings, context=f"Link {pred_id}->{succ_id}")

            lag_raw = _text(pl.find("./LinkLag"))
            lag_days = 0
            if lag_raw:
                try:
                    # tenths of a minute -> minutes
                    minutes = int(lag_raw) / 10.0
                    # convert to whole workdays (8h/day = 480 minutes)
                    lag_days = int(round(minutes / 480.0))
                except Exception:
                    warnings.append(f"Bad LinkLag '{lag_raw}' on link {pred_id}->{succ_id}. Using 0.")
                    lag_days = 0

            relationships.append(
                Relationship(
                    pred_id=str(pred_id),
                    succ_id=str(succ_id),
                    rel_type=rel_type,
                    lag_days=int(lag_days),
                )
            )

    return MSProjectImportResult(
        project_start=project_start,
        holidays=holidays,
        activities=activities,
        relationships=relationships,
        warnings=warnings,
    )


# -------------------------
# Helpers
# -------------------------

def _strip_namespaces(root: ET.Element) -> None:
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def _text(el: Optional[ET.Element]) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _parse_project_start(root: ET.Element, warnings: List[str]) -> Optional[date]:
    start_txt = _text(root.find("./StartDate")) or _text(root.find("./Project/StartDate"))
    if not start_txt:
        return None
    return _parse_dt_to_date(start_txt, warnings, context="Project StartDate")


def _parse_dt_to_date(dt_txt: str, warnings: List[str], context: str) -> Optional[date]:
    s = dt_txt.strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        warnings.append(f"{context}: could not parse date '{dt_txt}'")
        return None


_DURATION_RE = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)


def _parse_duration_to_days(duration_txt: str, warnings: List[str], context: str) -> int:
    """
    MSPDI Duration is commonly ISO-8601-like (P?DT?H?M?S).
    Convert to whole workdays using 8h/day (480 min/day).
    """
    s = duration_txt.strip()
    if not s:
        return 0

    m = _DURATION_RE.match(s)
    if not m:
        # sometimes exports may store raw minutes
        try:
            minutes = int(s)
            return int(round(minutes / 480.0))
        except Exception:
            warnings.append(f"{context}: unrecognized Duration '{duration_txt}'. Using 0.")
            return 0

    days = int(m.group("days") or 0)
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    seconds = int(m.group("seconds") or 0)

    total_minutes = days * 480 + hours * 60 + minutes + int(round(seconds / 60.0))
    return int(round(total_minutes / 480.0))


def _map_link_type(type_code: str, warnings: List[str], context: str) -> RelType:
    # MSPDI PredecessorLink Type:
    # 0=FF, 1=FS, 2=SF, 3=SS
    tc = (type_code or "").strip()
    if tc == "0":
        return RelType.FF
    if tc == "1":
        return RelType.FS
    if tc == "2":
        return RelType.SF
    if tc == "3":
        return RelType.SS
    warnings.append(f"{context}: unknown Type '{type_code}', defaulting to FS.")
    return RelType.FS


def _parse_project_holidays(root: ET.Element, warnings: List[str]) -> Set[date]:
    """
    Conservative: treat Calendar Exceptions as non-working (holidays).
    Collect <FromDate>..<ToDate> inclusive.
    """
    holidays: Set[date] = set()
    calendars_el = root.find("./Calendars") or root.find("./Project/Calendars")
    if calendars_el is None:
        return holidays

    for cal in calendars_el.findall("./Calendar"):
        excs = cal.find("./Exceptions")
        if excs is None:
            continue
        for exc in excs.findall("./Exception"):
            tp = exc.find("./TimePeriod")
            if tp is None:
                continue
            fd = _parse_dt_to_date(_text(tp.find("./FromDate")), warnings, context="Calendar Exception FromDate")
            td = _parse_dt_to_date(_text(tp.find("./ToDate")), warnings, context="Calendar Exception ToDate")
            if fd is None or td is None:
                continue
            if td < fd:
                fd, td = td, fd
            cur = fd
            while cur <= td:
                holidays.add(cur)
                cur += timedelta(days=1)

    return holidays