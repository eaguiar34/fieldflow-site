from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ResultsCompareSettings:
    show_changed_only: bool = True
    critical_only: bool = False
    sort_key: str = "delta_finish"  # delta_finish|delta_es|delta_ef|delta_ls|delta_lf|delta_tf|activity_id
    top_n: int = 200


@dataclass(frozen=True)
class ResultsDeltaRow:
    activity_id: str
    name: str

    base_es: str
    scen_es: str
    d_es: Optional[int]

    base_ef: str
    scen_ef: str
    d_ef: Optional[int]

    base_ls: str
    scen_ls: str
    d_ls: Optional[int]

    base_lf: str
    scen_lf: str
    d_lf: Optional[int]

    base_tf: Optional[int]
    scen_tf: Optional[int]
    d_tf: Optional[int]

    base_crit: bool
    scen_crit: bool
    crit_flip: bool

    negative_float: bool

    # Heuristic: how much the activity's finish moved (ΔEF), used as a proxy "driver".
    delta_finish_proxy: Optional[int]


def _safe_int(x) -> Optional[int]:
    return None if x is None else int(x)


def _fmt_date(calendar, project_start, day_index: Optional[int]) -> str:
    if day_index is None:
        return "—"
    return str(calendar.add_working_days(project_start, int(day_index)))


def _delta(a: Optional[int], b: Optional[int]) -> Optional[int]:
    if a is None or b is None:
        return None
    return int(b) - int(a)


def build_results_deltas(
    *,
    base_cpm,
    scen_cpm,
    base_activities: Dict[str, str],
    scen_activities: Dict[str, str],
    calendar,
    project_start,
) -> List[ResultsDeltaRow]:
    """Build per-activity CPM metric deltas (baseline vs scenario).

    Assumes base_cpm/scen_cpm are the objects returned by your compute_cpm_for_project wrapper.
    They must expose: metrics_by_id[act_id].es/ef/ls/lf/total_float.
    """

    base_metrics = getattr(base_cpm, "metrics_by_id")
    scen_metrics = getattr(scen_cpm, "metrics_by_id")

    common_ids = sorted(set(base_metrics.keys()) & set(scen_metrics.keys()))
    out: List[ResultsDeltaRow] = []

    for aid in common_ids:
        bm = base_metrics[aid]
        sm = scen_metrics[aid]

        b_es = _safe_int(getattr(bm, "es", None))
        s_es = _safe_int(getattr(sm, "es", None))
        b_ef = _safe_int(getattr(bm, "ef", None))
        s_ef = _safe_int(getattr(sm, "ef", None))
        b_ls = _safe_int(getattr(bm, "ls", None))
        s_ls = _safe_int(getattr(sm, "ls", None))
        b_lf = _safe_int(getattr(bm, "lf", None))
        s_lf = _safe_int(getattr(sm, "lf", None))

        b_tf = _safe_int(getattr(bm, "total_float", None))
        s_tf = _safe_int(getattr(sm, "total_float", None))

        base_crit = (b_tf == 0) if b_tf is not None else False
        scen_crit = (s_tf == 0) if s_tf is not None else False
        crit_flip = base_crit != scen_crit

        negative_float = (s_tf is not None and s_tf < 0)

        name = scen_activities.get(aid) or base_activities.get(aid) or aid

        d_ef = _delta(b_ef, s_ef)

        out.append(
            ResultsDeltaRow(
                activity_id=str(aid),
                name=str(name),
                base_es=_fmt_date(calendar, project_start, b_es),
                scen_es=_fmt_date(calendar, project_start, s_es),
                d_es=_delta(b_es, s_es),
                base_ef=_fmt_date(calendar, project_start, b_ef),
                scen_ef=_fmt_date(calendar, project_start, s_ef),
                d_ef=d_ef,
                base_ls=_fmt_date(calendar, project_start, b_ls),
                scen_ls=_fmt_date(calendar, project_start, s_ls),
                d_ls=_delta(b_ls, s_ls),
                base_lf=_fmt_date(calendar, project_start, b_lf),
                scen_lf=_fmt_date(calendar, project_start, s_lf),
                d_lf=_delta(b_lf, s_lf),
                base_tf=b_tf,
                scen_tf=s_tf,
                d_tf=_delta(b_tf, s_tf),
                base_crit=base_crit,
                scen_crit=scen_crit,
                crit_flip=crit_flip,
                negative_float=negative_float,
                delta_finish_proxy=d_ef,
            )
        )

    return out


def apply_settings(rows: List[ResultsDeltaRow], settings: ResultsCompareSettings) -> List[ResultsDeltaRow]:
    # Filters
    filtered = rows
    if settings.critical_only:
        filtered = [r for r in filtered if r.scen_crit]

    if settings.show_changed_only:
        def changed(r: ResultsDeltaRow) -> bool:
            return any(
                x not in (None, 0)
                for x in (r.d_es, r.d_ef, r.d_ls, r.d_lf, r.d_tf)
            ) or r.crit_flip or r.negative_float
        filtered = [r for r in filtered if changed(r)]

    # Sort
    key = settings.sort_key

    def sort_tuple(r: ResultsDeltaRow) -> Tuple:
        if key == "delta_es":
            v = r.d_es
        elif key == "delta_ef":
            v = r.d_ef
        elif key == "delta_ls":
            v = r.d_ls
        elif key == "delta_lf":
            v = r.d_lf
        elif key == "delta_tf":
            v = r.d_tf
        elif key == "activity_id":
            return (r.activity_id,)
        else:  # delta_finish (default)
            v = r.delta_finish_proxy

        # Sort None to bottom
        return (-(abs(v) if v is not None else -1), r.activity_id)

    if key == "activity_id":
        filtered.sort(key=lambda r: r.activity_id)
    else:
        filtered.sort(key=sort_tuple)

    # Top N
    if settings.top_n and settings.top_n > 0:
        filtered = filtered[: settings.top_n]

    return filtered


def summarize(rows: List[ResultsDeltaRow]) -> str:
    flips = sum(1 for r in rows if r.crit_flip)
    neg = sum(1 for r in rows if r.negative_float)
    return f"Rows: {len(rows)} | Critical flips: {flips} | Negative float: {neg}"
