from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, Tuple, Dict, List

from fieldflow.app.paths import get_default_db_path
from fieldflow.app.project_file import ProjectFile, load_project_file, save_project_file
from fieldflow.app.project_state import ProjectState
from fieldflow.domain.scheduling.types import Activity, Relationship, RelType
from fieldflow.app.scenarios import ProjectScenarios, ScenarioState
from fieldflow.infra.db.sqlite_store import (
    SQLiteStore,
    PersistedActivityRow,
    PersistedRelationshipRow,
)


def _to_iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _from_iso(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


@dataclass
class ControllerConfig:
    db_path: Path


class ProjectController:
    """
    App-layer spine:
      - manages current project_key (from .fieldflow OR workspace manifest)
      - loads/saves: calendar, baseline, scenarios, active scenario, last-used paths
    """

    def __init__(self, config: Optional[ControllerConfig] = None):
        if config is None:
            config = ControllerConfig(db_path=get_default_db_path())
        self.config = config
        self.store = SQLiteStore(self.config.db_path)
        self.store.initialize()

        self.project_file_path: Optional[Path] = None
        self.project: ProjectFile = ProjectFile(project_key="default", name="Default Project")
        self.store.ensure_project(self.project.project_key)

        # scenario name -> scenario_id (db)
        self._scenario_ids: Dict[str, int] = {}

    # -------------------------
    # Project file operations
    # -------------------------
    def open_project(self, path: Path) -> ProjectFile:
        pf = load_project_file(path)
        self.project_file_path = Path(path)
        self.project = pf
        self.store.ensure_project(pf.project_key)
        self._scenario_ids = {}
        return pf

    def open_project_identity(self, *, project_key: str, name: str = "Untitled Project") -> ProjectFile:
        """Open a project by identity without a .fieldflow file.

        Used by folder-packaged workspaces (project.ffproj.json).
        """
        project_key = (project_key or "").strip()
        if not project_key:
            raise ValueError("Invalid project identity: missing project_key")
        pf = ProjectFile(project_key=project_key, name=name or "Untitled Project")
        self.project_file_path = None
        self.project = pf
        self.store.ensure_project(pf.project_key)
        self._scenario_ids = {}
        return pf

    def save_project_as(self, path: Path, name: str) -> ProjectFile:
        pf = ProjectFile.new(name=name or "Untitled Project")
        save_project_file(path, pf)
        self.project_file_path = Path(path)
        self.project = pf
        self.store.ensure_project(pf.project_key)
        self._scenario_ids = {}
        return pf

    # -------------------------
    # Settings
    # -------------------------
    def load_settings_into_state(self, state: ProjectState) -> str:
        s = self.store.load_project_settings(self.project.project_key)
        if s.start_date_iso:
            state.project_start = _from_iso(s.start_date_iso) or state.project_start
        state.calendar.holidays = {d for d in (_from_iso(x) for x in s.holidays_iso) if d is not None}
        # return last active scenario name (or "Baseline")
        return s.active_scenario_name or "Baseline"

    def save_calendar_from_state(self, state: ProjectState) -> None:
        self.store.save_project_calendar(
            self.project.project_key,
            _to_iso(state.project_start),
            [d.isoformat() for d in state.calendar.holidays],
        )

    def get_last_used_paths(self) -> Tuple[Optional[str], Optional[str]]:
        s = self.store.load_project_settings(self.project.project_key)
        return s.last_activities_path, s.last_logic_path

    def save_last_used_paths(self, activities_path: Optional[str], logic_path: Optional[str]) -> None:
        self.store.save_last_used_paths(self.project.project_key, activities_path, logic_path)

    def save_active_scenario_name(self, active_name: str) -> None:
        self.store.save_active_scenario_name(self.project.project_key, active_name)

    # -------------------------
    # Baseline load/save
    # -------------------------
    def load_baseline_into(self, state: ProjectState) -> None:
        act_rows = self.store.load_baseline_activities(self.project.project_key)
        rel_rows = self.store.load_baseline_relationships(self.project.project_key)

        if act_rows:
            state.activities = [
                Activity(
                    id=r.id,
                    name=r.name,
                    duration_days=r.duration_days,
                    snet=_from_iso(r.snet_iso),
                    fnet=_from_iso(r.fnet_iso),
                )
                for r in act_rows
            ]

        if rel_rows:
            state.relationships = [
                Relationship(
                    pred_id=r.pred_id,
                    succ_id=r.succ_id,
                    rel_type=RelType(r.rel_type),
                    lag_days=r.lag_days,
                )
                for r in rel_rows
            ]

    def save_baseline_from(self, state: ProjectState) -> None:
        arows: List[PersistedActivityRow] = []
        for i, a in enumerate(state.activities):
            arows.append(
                PersistedActivityRow(
                    id=a.id,
                    name=a.name,
                    duration_days=int(a.duration_days),
                    snet_iso=_to_iso(a.snet),
                    fnet_iso=_to_iso(a.fnet),
                    sort_order=i,
                )
            )
        self.store.save_baseline_activities(self.project.project_key, arows)

        rrows: List[PersistedRelationshipRow] = []
        for i, r in enumerate(state.relationships):
            rrows.append(
                PersistedRelationshipRow(
                    pred_id=r.pred_id,
                    succ_id=r.succ_id,
                    rel_type=r.rel_type.value,
                    lag_days=int(r.lag_days),
                    sort_order=i,
                )
            )
        self.store.save_baseline_relationships(self.project.project_key, rrows)

    # -------------------------
    # Scenarios: load/save
    # -------------------------
    def refresh_scenario_index(self) -> None:
        self._scenario_ids = {s.name: s.scenario_id for s in self.store.list_scenarios(self.project.project_key)}

    def load_all_scenarios_into(self, proj: ProjectScenarios) -> None:
        """
        Loads scenarios from DB into the in-memory ProjectScenarios object.
        Baseline stays in proj.baseline; scenarios get appended.
        """
        self.refresh_scenario_index()
        proj.scenarios = []

        for name, sid in self._scenario_ids.items():
            act_rows = self.store.load_scenario_activities(self.project.project_key, sid)
            rel_rows = self.store.load_scenario_relationships(self.project.project_key, sid)

            activities = [
                Activity(r.id, r.name, r.duration_days, snet=_from_iso(r.snet_iso), fnet=_from_iso(r.fnet_iso))
                for r in act_rows
            ]
            relationships = [
                Relationship(rr.pred_id, rr.succ_id, RelType(rr.rel_type), rr.lag_days)
                for rr in rel_rows
            ]

            proj.scenarios.append(ScenarioState(name=name, activities=activities, relationships=relationships))

    def create_scenario_from_baseline(self, proj: ProjectScenarios, name: str) -> None:
        """
        Creates scenario in DB and in memory, seeded from baseline.
        """
        proj.create_scenario_from_baseline(name)

        sid = self.store.create_scenario(self.project.project_key, name)
        self._scenario_ids[name] = sid

        self.save_scenario_from_state(name, proj.get_active())

    def delete_scenario(self, proj: ProjectScenarios, name: str) -> None:
        if name == "Baseline":
            raise ValueError("Cannot delete Baseline.")
        self.refresh_scenario_index()
        sid = self._scenario_ids.get(name)
        if sid is not None:
            self.store.delete_scenario(self.project.project_key, sid)
        proj.scenarios = [s for s in proj.scenarios if s.name != name]
        if proj.active_name == name:
            proj.active_name = "Baseline"
            self.save_active_scenario_name("Baseline")
        self.refresh_scenario_index()

    def save_scenario_from_state(self, scenario_name: str, state: ScenarioState) -> None:
        self.refresh_scenario_index()
        sid = self._scenario_ids.get(scenario_name)
        if sid is None:
            sid = self.store.create_scenario(self.project.project_key, scenario_name)
            self._scenario_ids[scenario_name] = sid

        arows: List[PersistedActivityRow] = []
        for i, a in enumerate(state.activities):
            arows.append(
                PersistedActivityRow(
                    id=a.id,
                    name=a.name,
                    duration_days=int(a.duration_days),
                    snet_iso=_to_iso(a.snet),
                    fnet_iso=_to_iso(a.fnet),
                    sort_order=i,
                )
            )
        self.store.save_scenario_activities(self.project.project_key, sid, arows)

        rrows: List[PersistedRelationshipRow] = []
        for i, r in enumerate(state.relationships):
            rrows.append(
                PersistedRelationshipRow(
                    pred_id=r.pred_id,
                    succ_id=r.succ_id,
                    rel_type=r.rel_type.value,
                    lag_days=int(r.lag_days),
                    sort_order=i,
                )
            )
        self.store.save_scenario_relationships(self.project.project_key, sid, rrows)

    # -------------------------
    # Autosave entrypoint
    # -------------------------
    def autosave(self, ps: ProjectState, proj: ProjectScenarios) -> None:
        """
        Saves calendar + active scenario name, then saves baseline or active scenario data.
        """
        self.save_calendar_from_state(ps)