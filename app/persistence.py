from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from fieldflow.app.paths import get_default_db_path
from fieldflow.domain.scheduling.types import Activity
from fieldflow.infra.db.sqlite_store import SQLiteStore


def _to_iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _from_iso(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


@dataclass
class PersistenceConfig:
    db_path: Path
    project_key: str = "default"  # later: file path, GUID, etc.


class ProjectPersistence:
    """App-layer persistence service. Domain stays pure."""

    def __init__(self, config: Optional[PersistenceConfig] = None):
        if config is None:
            config = PersistenceConfig(db_path=get_default_db_path())
        self.config = config
        self.store = SQLiteStore(self.config.db_path)
        self.store.initialize()
        self.store.ensure_project(self.config.project_key)

    # -------------------------
    # Calendar
    # -------------------------
    def load_calendar_into_state(self, state) -> None:
        """Loads start_date + holidays from SQLite into a ProjectState-like object."""
        settings = self.store.load_project_settings(self.config.project_key)

        if settings.start_date_iso:
            state.project_start = _from_iso(settings.start_date_iso)

        holidays: Set[date] = {d for d in (_from_iso(x) for x in settings.holidays_iso) if d is not None}

        # WorkCalendar in your domain exposes .holidays (mutable set[date])
        if hasattr(state.calendar, "holidays"):
            state.calendar.holidays = holidays
        elif hasattr(state.calendar, "set_holidays"):
            state.calendar.set_holidays(holidays)
        else:
            raise AttributeError("WorkCalendar must expose holidays via .holidays or set_holidays(...)")

    def save_calendar_from_state(self, state) -> None:
        """Saves start_date + holidays from a ProjectState-like object into SQLite."""
        start_iso = _to_iso(getattr(state, "project_start", None))

        if hasattr(state.calendar, "holidays"):
            holidays = getattr(state.calendar, "holidays")
        elif hasattr(state.calendar, "get_holidays"):
            holidays = state.calendar.get_holidays()
        else:
            raise AttributeError("WorkCalendar must expose holidays via .holidays or get_holidays()")

        holidays_iso = sorted(d.isoformat() for d in holidays)
        self.store.save_project_calendar(self.config.project_key, start_iso, holidays_iso)

    # -------------------------
    # Constraints (SNET/FNET)
    # -------------------------
    def load_constraints_into_state(self, state) -> None:
        """Loads SNET/FNET from SQLite and applies them to matching activities."""
        persisted = self.store.load_constraints(self.config.project_key)

        activities = getattr(state, "activities", None)
        if activities is None:
            raise AttributeError("ProjectState must have .activities")

        # Domain Activity is a frozen dataclass, so rebuild activities.
        rebuilt: list[Activity] = []
        for act in activities:
            snet_iso, fnet_iso = persisted.by_activity.get(str(act.id), (None, None))
            rebuilt.append(
                Activity(
                    act.id,
                    act.name,
                    act.duration_days,
                    snet=_from_iso(snet_iso),
                    fnet=_from_iso(fnet_iso),
                )
            )

        state.activities = rebuilt

    def save_constraints_from_state(self, state) -> None:
        """Saves SNET/FNET for all activities into SQLite."""
        activities = getattr(state, "activities", None)
        if activities is None:
            raise AttributeError("ProjectState must have .activities")

        constraints: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        for act in activities:
            constraints[str(act.id)] = (_to_iso(act.snet), _to_iso(act.fnet))

        self.store.upsert_constraints(self.config.project_key, constraints)

        # Optional cleanup (non-critical)
        try:
            self.store.delete_constraints_not_in(self.config.project_key, [a.id for a in activities])
        except Exception:
            pass