from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import date

from fieldflow.domain.scheduling.calendar import WorkCalendar


class RelType(str, Enum):
    FS = "FS"
    SS = "SS"
    FF = "FF"
    SF = "SF"


@dataclass(frozen=True)
class Activity:
    id: str
    name: str
    duration_days: int  # WORKING days
    snet: date | None = None  # Start No Earlier Than
    fnet: date | None = None  # Finish No Earlier Than


@dataclass(frozen=True)
class Relationship:
    pred_id: str
    succ_id: str
    rel_type: RelType = RelType.FS
    lag_days: int = 0  # WORKING days


@dataclass(frozen=True)
class Schedule:
    project_start: date
    calendar: WorkCalendar
    activities: list[Activity]
    relationships: list[Relationship]
