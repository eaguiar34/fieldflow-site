from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional


@dataclass(frozen=True)
class GanttBar:
    activity_id: str
    name: str
    start: date
    finish: date
    is_critical: bool
    total_float: Optional[int]


def build_gantt_bars(*, activities_by_id: Dict[str, str], cpm, calendar, project_start: date) -> List[GanttBar]:
    """Small hook for a future Gantt dock.

    Uses CPM metrics (ES/EF) converted to calendar dates.
    """
    bars: List[GanttBar] = []
    metrics_by_id = getattr(cpm, "metrics_by_id")

    for aid, m in metrics_by_id.items():
        es = getattr(m, "es", None)
        ef = getattr(m, "ef", None)
        if es is None or ef is None:
            continue
        start = calendar.add_working_days(project_start, int(es))
        finish = calendar.add_working_days(project_start, int(ef))
        tf = getattr(m, "total_float", None)
        is_crit = (tf == 0) if tf is not None else False
        bars.append(
            GanttBar(
                activity_id=str(aid),
                name=str(activities_by_id.get(str(aid), str(aid))),
                start=start,
                finish=finish,
                is_critical=is_crit,
                total_float=tf,
            )
        )

    bars.sort(key=lambda b: (b.start, b.activity_id))
    return bars
