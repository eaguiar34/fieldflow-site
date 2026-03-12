from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, Set, Tuple, List

from PySide6.QtCore import QObject, Signal, QSettings

from fieldflow.app.project_controller import ProjectController
from fieldflow.app.project_state import ProjectState
from fieldflow.app.scenarios import ProjectScenarios, ScenarioState
from fieldflow.app.services import activities_from_import, activities_to_domain, relationships_from_import
from fieldflow.domain.scheduling.calendar import WorkCalendar
from fieldflow.infra.integrations.csv_importer import import_activities_csv
from fieldflow.infra.integrations.logic_csv_importer import import_logic_csv
from fieldflow.infra.integrations.msproject_xml_importer import import_msproject_xml
from fieldflow.app.workspace.workspace import ProjectWorkspace
from fieldflow.app.workspace.lock_manager import LockManager
from fieldflow.app.workspace.event_log import EventLog
from fieldflow.app.workspace.snapshots import SnapshotManager
from fieldflow.app.workspace.sync import SharedFolderEventSync

import uuid


class AppSignals(QObject):
    project_loaded = Signal()
    active_scenario_changed = Signal(str)
    calendar_changed = Signal()
    data_changed = Signal()
    schedule_computed = Signal()
    schedule_compared = Signal()

    ui_zoom_changed = Signal(int)     # percent
    ui_theme_changed = Signal(str)    # "light" | "dark"
    recent_projects_changed = Signal()


@dataclass
class ScheduleResults:
    active: Optional[object] = None
    baseline: Optional[object] = None
    compared_active_name: str = "Baseline"


class AppContext:
    def __init__(self) -> None:
        self.controller = ProjectController()
        self.project = ProjectScenarios.empty()

        self.calendar = WorkCalendar()
        self.project_start: date = date.today()

        self.signals = AppSignals()
        self.results = ScheduleResults()

        self.qsettings = QSettings("FieldFlow", "FieldFlow")

        self.project.set_active("Baseline")
        self.load_from_db()

        self.workspace: Optional[ProjectWorkspace] = None
        self.lock: Optional[LockManager] = None
        self.event_log: Optional[EventLog] = None
        self.snapshots: Optional[SnapshotManager] = None
        self.sync: Optional[SharedFolderEventSync] = None

        self.is_read_only: bool = False
        self.lock_owned: bool = False
        self.lock_status: str = ""

    @property
    def project_key(self) -> str:
        return self.controller.project.project_key

    def settings_prefix(self) -> str:
        return f"projects/{self.project_key}"

    def open_workspace_folder(self, folder: Path) -> None:
        ws = ProjectWorkspace(folder)
        ws.ensure_layout()

        self.workspace = ws
        self.lock = LockManager(ws.locks_dir / "project.lock")
        self.event_log = EventLog(ws.events_dir / "events.jsonl")
        self.snapshots = SnapshotManager(ws.root)

        # Ensure stable project identity for DB + sharing.
        if not ws.project_key:
            ws.project_key = str(uuid.uuid4())
            ws.project_name = ws.project_name or ws.root.name
            try:
                ws.save_manifest()
            except Exception:
                pass

        # Switch controller to workspace identity.
        self.controller.open_project_identity(project_key=ws.project_key, name=ws.project_name)
        self.project = ProjectScenarios.empty()
        self.project.set_active("Baseline")
        self.load_from_db()

        # Shared-folder sync engine (safe even for local folders).
        self.sync = SharedFolderEventSync(ws.events_dir, actor=ws.current_user())

        # role-based read-only (even if lock free)
        self.is_read_only = not ws.user_can_edit()

        # Attempt to acquire edit lock if allowed.
        self.acquire_edit_lock()

        self.add_recent_project(ws.root)

    def acquire_edit_lock(self) -> None:
        """Try to acquire the workspace lock; fall back to read-only."""
        self.lock_owned = False
        self.lock_status = ""
        if self.is_read_only or not self.lock:
            self.lock_status = "Read-only (role)"
            return

        ok = self.lock.acquire(lease_seconds=90)
        if ok:
            self.lock_owned = True
            self.lock_status = "Lock acquired"
            return

        info = self.lock.read()
        if info is None:
            self.is_read_only = True
            self.lock_status = "Read-only (lock unavailable)"
            return

        self.is_read_only = True
        self.lock_status = f"Read-only (locked by {info.owner}@{info.machine} until {info.expires_utc})"

    def renew_lock_if_owned(self) -> None:
        if not self.lock or not self.lock_owned or self.is_read_only:
            return
        self.lock.renew(lease_seconds=90)

    def release_lock_if_owned(self) -> None:
        if not self.lock or not self.lock_owned:
            return
        self.lock.release()
        self.lock_owned = False

    def append_event(self, entity: str, entity_id: str, op: str, payload: dict) -> None:
        """Append to outbox + merged event log (best-effort)."""
        if not self.workspace:
            return
        actor = self.workspace.current_user()
        try:
            if self.sync is not None:
                self.sync.append_local(entity=entity, entity_id=entity_id, op=op, payload=payload)
        except Exception:
            pass
        try:
            if self.event_log is not None:
                self.event_log.append_simple(actor=actor, entity=entity, entity_id=entity_id, op=op, payload=payload)
        except Exception:
            pass

    def merge_events_now(self) -> None:
        if self.sync is None:
            return
        try:
            self.sync.merge()
        except Exception:
            pass

    def workspace_status_text(self) -> str:
        if not self.workspace:
            return ""
        ws = self.workspace
        ro = "READ-ONLY" if self.is_read_only else "EDIT"
        lib = ws.shared_library_root or "(local)"
        lock = self.lock_status or ("Lock" if self.lock_owned else "")
        lock_part = f" | {lock}" if lock else ""
        return f"Workspace: {ws.root} | Mode: {ro}{lock_part} | Libraries: {lib}"

    # ------------ onboarding (global) ------------
    def onboarding_done(self) -> bool:
        v = self.qsettings.value("ui/onboarding_done", False)
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "y", "on")

    def set_onboarding_done(self, done: bool = True) -> None:
        self.qsettings.setValue("ui/onboarding_done", bool(done))

    # ------------ UI prefs: zoom ------------
    def get_zoom_percent(self) -> int:
        v = self.qsettings.value(f"{self.settings_prefix()}/ui/zoom_percent", 100)
        try:
            return int(v)
        except Exception:
            return 100

    def set_zoom_percent(self, percent: int) -> None:
        percent = max(70, min(160, int(percent)))
        self.qsettings.setValue(f"{self.settings_prefix()}/ui/zoom_percent", percent)
        self.signals.ui_zoom_changed.emit(percent)

    # ------------ UI prefs: theme ------------
    def get_theme(self) -> str:
        v = self.qsettings.value(f"{self.settings_prefix()}/ui/theme", "light")
        return str(v) if str(v) in ("light", "dark") else "light"

    def set_theme(self, theme: str) -> None:
        theme = theme if theme in ("light", "dark") else "light"
        self.qsettings.setValue(f"{self.settings_prefix()}/ui/theme", theme)
        self.signals.ui_theme_changed.emit(theme)

    # ------------ recent projects ------------
    def recent_projects(self) -> List[str]:
        v = self.qsettings.value("ui/recent_projects", [])
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x) for x in v if str(x)]
        return []

    def _set_recent_projects(self, paths: List[str]) -> None:
        self.qsettings.setValue("ui/recent_projects", paths[:10])
        self.signals.recent_projects_changed.emit()

    def add_recent_project(self, path: Path) -> None:
        p = str(path)
        paths = [x for x in self.recent_projects() if x != p]
        paths.insert(0, p)
        self._set_recent_projects(paths)

    # ------------ state access ------------
    def active(self) -> ScenarioState:
        return self.project.get_active()

    # ------------ load/save ------------
    def load_from_db(self) -> None:
        ps = ProjectState.empty()
        ps.project_start = self.project_start
        ps.calendar = self.calendar

        active_name = self.controller.load_settings_into_state(ps)

        self.controller.load_baseline_into(ps)
        self.project.baseline.activities = list(ps.activities)
        self.project.baseline.relationships = list(ps.relationships)

        self.controller.load_all_scenarios_into(self.project)

        self.calendar = ps.calendar
        self.project_start = self.calendar.next_working_day(ps.project_start)

        if active_name != "Baseline" and any(s.name == active_name for s in self.project.scenarios):
            self.project.active_name = active_name
        else:
            self.project.active_name = "Baseline"

        self.signals.project_loaded.emit()
        self.signals.active_scenario_changed.emit(self.project.active_name)
        self.signals.calendar_changed.emit()

    def autosave(self) -> None:
        if self.is_read_only:
            return
        ps = ProjectState.empty()
        ps.project_start = self.project_start
        ps.calendar = self.calendar
        ps.activities = list(self.active().activities)
        ps.relationships = list(self.active().relationships)
        self.controller.autosave(ps, self.project)
        self.signals.data_changed.emit()

        self.append_event(
            entity="project",
            entity_id=self.project_key,
            op="autosave",
            payload={"active_scenario": self.project.active_name},
        )

    def set_active_scenario(self, name: str) -> None:
        self.project.set_active(name)
        self.controller.save_active_scenario_name(self.project.active_name)
        self.signals.active_scenario_changed.emit(self.project.active_name)
        self.signals.data_changed.emit()

    def update_calendar(self, *, start: Optional[date] = None, holidays: Optional[Set[date]] = None) -> None:
        if self.is_read_only:
            return
        if start is not None:
            self.project_start = self.calendar.next_working_day(start)
        if holidays is not None:
            self.calendar.holidays = set(holidays)
        self.autosave()
        self.signals.calendar_changed.emit()

    # ------------ project file ops ------------
    def open_project_file(self, path: Path) -> None:
        self.controller.open_project(path)
        self.add_recent_project(path)
        self.load_from_db()

    def save_project_as(self, path: Path, name: str) -> None:
        self.controller.save_project_as(path, name=name)
        self.add_recent_project(path)
        self.autosave()
        self.signals.project_loaded.emit()

    # ------------ imports ------------
    def import_activities(self, path: Path) -> Tuple[int, str]:
        if self.is_read_only:
            return 0, "Read-only"
        imported = import_activities_csv(str(path))
        rows = activities_from_import([(a.id, a.name, a.duration_days) for a in imported])
        self.active().activities = activities_to_domain(rows)
        self.autosave()

        self.append_event(
            entity="activities",
            entity_id=self.project_key,
            op="import_csv",
            payload={"path": str(path), "rows": len(rows)},
        )
        return len(rows), str(path)

    def import_logic(self, path: Path) -> Tuple[int, str]:
        if self.is_read_only:
            return 0, "Read-only"
        imported = import_logic_csv(str(path))
        rel_tuples = [(r.pred_id, r.succ_id, r.rel_type, r.lag_days) for r in imported]
        rels = relationships_from_import(rel_tuples)
        self.active().relationships = rels
        self.autosave()

        self.append_event(
            entity="logic",
            entity_id=self.project_key,
            op="import_csv",
            payload={"path": str(path), "rows": len(rels)},
        )
        return len(rels), str(path)

    def import_msproject_xml_into_active(self, path: Path, *, update_calendar: bool = True) -> Tuple[int, int, int]:
        if self.is_read_only:
            return 0, 0, 0
        res = import_msproject_xml(str(path))
        if update_calendar:
            if res.project_start:
                self.project_start = self.calendar.next_working_day(res.project_start)
            self.calendar.holidays = set(res.holidays)
            self.signals.calendar_changed.emit()

        self.active().activities = list(res.activities)
        self.active().relationships = list(res.relationships)
        self.autosave()

        self.append_event(
            entity="msproject",
            entity_id=self.project_key,
            op="import_xml",
            payload={"path": str(path), "activities": len(res.activities), "relationships": len(res.relationships)},
        )
        return len(res.activities), len(res.relationships), len(res.holidays)