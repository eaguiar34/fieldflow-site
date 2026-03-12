from __future__ import annotations

"""Schedule-driven cost forecast.

Design goal: keep forecasting explainable and deterministic.

We distribute each Work Package's *total cost* across weekly buckets spanning the
earliest ES to the latest EF of its linked activities.

Curve styles (per WP):
  - linear: uniform (but still respects working-day availability)
  - front: front-loaded
  - back:  back-loaded
  - bell:  mid-peaked

Notes:
  - Offline-first: no external libs.
  - We don't change CPM logic; we consume ES/EF dates already produced.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Tuple

from fieldflow.app.controls_models import WorkPackage
from fieldflow.domain.scheduling.calendar import WorkCalendar


@dataclass
class WeeklyBucket:
    week_start: date
    cost: float

    # Back-compat with an earlier attribute name ("amount").
    @property
    def amount(self) -> float:  # pragma: no cover
        return self.cost


def _week_start(d: date) -> date:
    # Monday as week start
    return d - timedelta(days=d.weekday())


def _curve_weights(n: int, style: str) -> List[float]:
    """Return a normalized list of weights of length n."""
    n = max(1, int(n))
    style = (style or "linear").strip().lower()

    if n == 1:
        return [1.0]

    if style == "front":
        raw = [float(n - i) for i in range(n)]
    elif style == "back":
        raw = [float(i + 1) for i in range(n)]
    elif style == "bell":
        # Simple tent/triangular distribution (fast + explainable)
        mid = (n - 1) / 2.0
        raw = [max(0.1, (mid + 1.0) - abs(i - mid)) for i in range(n)]
    else:
        raw = [1.0 for _ in range(n)]

    s = sum(raw) or 1.0
    return [x / s for x in raw]


def _working_days_per_week(
    *,
    start: date,
    finish: date,
    calendar: WorkCalendar,
    weeks: List[date],
) -> List[int]:
    """Count working days *within* [start, finish] per weekly bucket."""
    if not weeks:
        return []

    idx_by_week = {w: i for i, w in enumerate(weeks)}
    counts = [0 for _ in weeks]

    cur = start
    while cur <= finish:
        w = _week_start(cur)
        i = idx_by_week.get(w)
        if i is not None and calendar.is_working_day(cur):
            counts[i] += 1
        cur += timedelta(days=1)

    # Avoid all-zero (e.g., range only hits weekends)
    if sum(counts) == 0:
        return [1 for _ in weeks]
    return counts


def build_weekly_cost_forecast(
    *,
    work_packages: List[WorkPackage],
    activity_es_by_id: Dict[str, date],
    activity_ef_by_id: Dict[str, date],
    calendar: WorkCalendar,
) -> Tuple[List[WeeklyBucket], List[str]]:
    """Build schedule-driven weekly forecast buckets."""

    warnings: List[str] = []
    buckets_by_week: Dict[date, float] = {}

    # Reference week for items without dates
    any_date = None
    if activity_es_by_id:
        any_date = min(activity_es_by_id.values())
    elif activity_ef_by_id:
        any_date = min(activity_ef_by_id.values())
    ref_week = _week_start(any_date) if any_date else _week_start(date.today())

    for wp in work_packages or []:
        total = float(wp.total_cost())

        ids = [x.strip() for x in (wp.linked_activity_ids or "").split(",") if x.strip()]
        if not ids:
            buckets_by_week[ref_week] = buckets_by_week.get(ref_week, 0.0) + total
            warnings.append(f"{wp.id}: no linked activities; forecast placed in {ref_week}")
            continue

        es_dates = [activity_es_by_id.get(i) for i in ids if activity_es_by_id.get(i)]
        ef_dates = [activity_ef_by_id.get(i) for i in ids if activity_ef_by_id.get(i)]

        if not es_dates and not ef_dates:
            buckets_by_week[ref_week] = buckets_by_week.get(ref_week, 0.0) + total
            warnings.append(f"{wp.id}: linked activities missing dates; forecast placed in {ref_week}")
            continue

        start = min(es_dates) if es_dates else min(ef_dates)
        finish = max(ef_dates) if ef_dates else max(es_dates)
        if finish < start:
            start, finish = finish, start

        ws = _week_start(start)
        we = _week_start(finish)

        weeks: List[date] = []
        cur = ws
        while cur <= we:
            weeks.append(cur)
            cur = cur + timedelta(days=7)

        if not weeks:
            buckets_by_week[ref_week] = buckets_by_week.get(ref_week, 0.0) + total
            continue

        avail = _working_days_per_week(start=start, finish=finish, calendar=calendar, weeks=weeks)
        shape = _curve_weights(len(weeks), getattr(wp, "curve_style", "linear"))

        raw = [float(a) * float(s) for a, s in zip(avail, shape)]
        sraw = sum(raw) or 1.0
        weights = [x / sraw for x in raw]

        for w, wt in zip(weeks, weights):
            buckets_by_week[w] = buckets_by_week.get(w, 0.0) + (total * wt)

    out = [WeeklyBucket(week_start=k, cost=v) for k, v in sorted(buckets_by_week.items(), key=lambda t: t[0])]
    return out, warnings