from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fieldflow.app.project_state import ProjectState
from fieldflow.domain.scheduling.cpm import CPMResult, compute_cpm
from fieldflow.domain.scheduling.types import Activity, RelType, Relationship


@dataclass(frozen=True)
class ActivityRow:
    id: str
    name: str
    duration_days: int
    snet: date | None = None
    fnet: date | None = None
    es: int | None = None
    ef: int | None = None
    ls: int | None = None
    lf: int | None = None
    total_float_days: int | None = None


def load_demo_activities() -> list[ActivityRow]:
    return [
        ActivityRow("A001", "Mobilize", 5),
        ActivityRow("A002", "Excavation", 10),
        ActivityRow("A003", "Formwork", 7),
        ActivityRow("A004", "Pour concrete", 3),
        ActivityRow("A005", "Cure / Strip", 4),
    ]


def activities_from_import(imported: list[tuple[str, str, int]]) -> list[ActivityRow]:
    return [ActivityRow(aid, name, dur) for (aid, name, dur) in imported]


def activities_to_domain(rows: list[ActivityRow]) -> list[Activity]:
    return [
        Activity(
            id=r.id,
            name=r.name,
            duration_days=r.duration_days,
            snet=r.snet,
            fnet=r.fnet,
        )
        for r in rows
    ]


def relationships_from_import(imported: list[tuple[str, str, str, int]]) -> list[Relationship]:
    out: list[Relationship] = []
    for pred, succ, rtype, lag in imported:
        rt = RelType(rtype.upper())
        out.append(Relationship(pred_id=pred, succ_id=succ, rel_type=rt, lag_days=int(lag)))
    return out


def compute_cpm_for_project(state: ProjectState) -> CPMResult:
    return compute_cpm(state.to_schedule())


def apply_cpm_to_rows(rows: list[ActivityRow], cpm: CPMResult) -> list[ActivityRow]:
    out: list[ActivityRow] = []
    for r in rows:
        m = cpm.metrics_by_id.get(r.id)
        if m is None:
            out.append(r)
            continue
        out.append(
            ActivityRow(
                id=r.id,
                name=r.name,
                duration_days=r.duration_days,
                snet=r.snet,
                fnet=r.fnet,
                es=m.es,
                ef=m.ef,
                ls=m.ls,
                lf=m.lf,
                total_float_days=m.total_float,
            )
        )
    return out
