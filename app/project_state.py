from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fieldflow.domain.scheduling.calendar import WorkCalendar
from fieldflow.domain.scheduling.types import Activity, Relationship, Schedule


@dataclass
class ProjectState:
    activities: list[Activity]
    relationships: list[Relationship]
    project_start: date
    calendar: WorkCalendar
    db_path: Path | None = None

    @classmethod
    def empty(cls) -> "ProjectState":
        return cls(
            activities=[],
            relationships=[],
            project_start=date.today(),
            calendar=WorkCalendar(),
            db_path=None,
        )

    def to_schedule(self) -> Schedule:
        return Schedule(
            project_start=self.project_start,
            calendar=self.calendar,
            activities=self.activities,
            relationships=self.relationships,
        )
