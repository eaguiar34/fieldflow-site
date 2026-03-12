from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict, deque

from fieldflow.domain.scheduling.types import RelType, Schedule


@dataclass(frozen=True)
class ActivityMetrics:
    es: int
    ef: int
    ls: int
    lf: int
    total_float: int


@dataclass(frozen=True)
class CPMResult:
    project_duration: int
    metrics_by_id: dict[str, ActivityMetrics]
    topo_order: list[str]


class CPMError(Exception):
    def __init__(self, message: str, cycle_path: list[str] | None = None):
        super().__init__(message)
        self.cycle_path = cycle_path or []


def _edge_weight_days(rel_type: RelType, pred_dur: int, succ_dur: int, lag: int) -> int:
    if rel_type == RelType.FS:
        return pred_dur + lag
    if rel_type == RelType.SS:
        return lag
    if rel_type == RelType.FF:
        return pred_dur - succ_dur + lag
    if rel_type == RelType.SF:
        return lag - succ_dur
    raise CPMError(f"Unsupported relationship type: {rel_type}")


def _find_cycle_path(nodes: list[str], edges: list[tuple[str, str]]) -> list[str]:
    graph: dict[str, list[str]] = defaultdict(list)
    for u, v in edges:
        graph[u].append(v)

    visited: set[str] = set()
    in_stack: set[str] = set()
    parent: dict[str, str | None] = {}

    def dfs(u: str) -> list[str]:
        visited.add(u)
        in_stack.add(u)
        for v in graph.get(u, []):
            if v not in visited:
                parent[v] = u
                cyc = dfs(v)
                if cyc:
                    return cyc
            elif v in in_stack:
                path = [v]
                cur = u
                while cur != v and cur is not None:
                    path.append(cur)
                    cur = parent.get(cur)
                path.append(v)
                path.reverse()
                return path
        in_stack.remove(u)
        return []

    for n in nodes:
        if n not in visited:
            parent[n] = None
            cyc = dfs(n)
            if cyc:
                return cyc
    return []


def compute_cpm(schedule: Schedule) -> CPMResult:
    acts = {a.id: a for a in schedule.activities}
    if not acts:
        raise CPMError("Schedule has no activities.")

    succs: dict[str, list[str]] = defaultdict(list)
    preds: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = {aid: 0 for aid in acts.keys()}

    weights: dict[tuple[str, str], int] = {}
    edge_list: list[tuple[str, str]] = []

    for rel in schedule.relationships:
        if rel.pred_id not in acts:
            raise CPMError(f"Logic references missing predecessor activity: {rel.pred_id}")
        if rel.succ_id not in acts:
            raise CPMError(f"Logic references missing successor activity: {rel.succ_id}")

        pred = acts[rel.pred_id]
        succ = acts[rel.succ_id]
        w = _edge_weight_days(rel.rel_type, pred.duration_days, succ.duration_days, rel.lag_days)

        succs[rel.pred_id].append(rel.succ_id)
        preds[rel.succ_id].append(rel.pred_id)
        indeg[rel.succ_id] += 1
        weights[(rel.pred_id, rel.succ_id)] = w
        edge_list.append((rel.pred_id, rel.succ_id))

    q = deque([aid for aid, d in indeg.items() if d == 0])
    topo: list[str] = []
    while q:
        n = q.popleft()
        topo.append(n)
        for s in succs.get(n, []):
            indeg[s] -= 1
            if indeg[s] == 0:
                q.append(s)

    if len(topo) != len(acts):
        cycle = _find_cycle_path(list(acts.keys()), edge_list)
        msg = "Schedule logic has a cycle (cannot compute CPM)."
        if cycle:
            msg += " Cycle: " + " -> ".join(cycle)
        raise CPMError(msg, cycle_path=cycle)

    cal = schedule.calendar
    es: dict[str, int] = {aid: 0 for aid in acts.keys()}
    ef: dict[str, int] = {}

    for aid in topo:
        a = acts[aid]
        if a.snet is not None:
            snet_idx = cal.working_day_index(schedule.project_start, a.snet, snap_forward=True)
            es[aid] = max(es[aid], snet_idx)
        if a.fnet is not None:
            fnet_idx = cal.working_day_index(schedule.project_start, a.fnet, snap_forward=True)
            es[aid] = max(es[aid], fnet_idx - a.duration_days)

        ef[aid] = es[aid] + a.duration_days

        for s in succs.get(aid, []):
            w = weights[(aid, s)]
            es[s] = max(es[s], es[aid] + w)

    project_duration = max(ef.values()) if ef else 0

    ls: dict[str, int] = {aid: project_duration - acts[aid].duration_days for aid in acts.keys()}
    for aid in reversed(topo):
        for p in preds.get(aid, []):
            w = weights[(p, aid)]
            ls[p] = min(ls[p], ls[aid] - w)

    metrics: dict[str, ActivityMetrics] = {}
    for aid, a in acts.items():
        es_i = es[aid]
        ef_i = es_i + a.duration_days
        ls_i = ls[aid]
        lf_i = ls_i + a.duration_days
        tf = ls_i - es_i
        metrics[aid] = ActivityMetrics(es=es_i, ef=ef_i, ls=ls_i, lf=lf_i, total_float=tf)

    return CPMResult(project_duration=project_duration, metrics_by_id=metrics, topo_order=topo)
