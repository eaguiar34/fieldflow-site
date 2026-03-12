from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fieldflow.domain.scheduling.types import Activity, Relationship


@dataclass(frozen=True)
class ChangeSummary:
    changed_durations: list[tuple[str, int, int]]  # (activity_id, baseline_dur, scenario_dur)
    added_relationships: list[Relationship]
    removed_relationships: list[Relationship]


def _rel_key(r: Relationship) -> tuple[str, str, str, int]:
    return (r.pred_id, r.succ_id, r.rel_type.value, int(r.lag_days))


def compare_baseline_to_scenario(
    baseline_acts: list[Activity],
    baseline_rels: list[Relationship],
    scenario_acts: list[Activity],
    scenario_rels: list[Relationship],
) -> ChangeSummary:
    b_dur = {a.id: int(a.duration_days) for a in baseline_acts}
    s_dur = {a.id: int(a.duration_days) for a in scenario_acts}

    changed: list[tuple[str, int, int]] = []
    for aid, bd in b_dur.items():
        sd = s_dur.get(aid)
        if sd is None:
            continue
        if sd != bd:
            changed.append((aid, bd, sd))
    changed.sort(key=lambda x: x[0])

    b_set = {_rel_key(r): r for r in baseline_rels}
    s_set = {_rel_key(r): r for r in scenario_rels}

    added = [s_set[k] for k in s_set.keys() - b_set.keys()]
    removed = [b_set[k] for k in b_set.keys() - s_set.keys()]

    added.sort(key=_rel_key)
    removed.sort(key=_rel_key)

    return ChangeSummary(
        changed_durations=changed,
        added_relationships=added,
        removed_relationships=removed,
    )