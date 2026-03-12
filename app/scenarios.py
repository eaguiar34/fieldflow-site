from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fieldflow.domain.scheduling.types import Activity, Relationship, Schedule


@dataclass
class ScenarioState:
    name: str
    activities: list[Activity]
    relationships: list[Relationship]

    def to_schedule(self) -> Schedule:
        return Schedule(activities=self.activities, relationships=self.relationships)


@dataclass
class ProjectScenarios:
    """
    v0 scenario system (in-memory only):
    - baseline + N scenarios
    - editing affects the active scenario
    """
    baseline: ScenarioState
    scenarios: list[ScenarioState]
    active_name: str
    db_path: Path | None = None  # baseline-only persistence for now

    @classmethod
    def empty(cls) -> "ProjectScenarios":
        empty_state = ScenarioState(name="Baseline", activities=[], relationships=[])
        return cls(baseline=empty_state, scenarios=[], active_name="Baseline", db_path=None)

    def get_active(self) -> ScenarioState:
        if self.active_name == "Baseline":
            return self.baseline
        for s in self.scenarios:
            if s.name == self.active_name:
                return s
        # fallback
        return self.baseline

    def set_active(self, name: str) -> None:
        self.active_name = name

    def create_scenario_from_baseline(self, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Scenario name cannot be empty.")
        if name == "Baseline":
            raise ValueError("Scenario name cannot be 'Baseline'.")
        if any(s.name == name for s in self.scenarios):
            raise ValueError("A scenario with that name already exists.")

        # copy baseline lists (shallow copy is fine because Activity/Relationship are immutable dataclasses)
        new_state = ScenarioState(
            name=name,
            activities=list(self.baseline.activities),
            relationships=list(self.baseline.relationships),
        )
        self.scenarios.append(new_state)
        self.active_name = name