from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from fieldflow.app.services import ActivityRow
from fieldflow.app.compare import ChangeSummary


def export_activity_metrics_csv(path: str | Path, rows: list[ActivityRow]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["id", "name", "duration_days", "es", "ef", "ls", "lf", "total_float_days"]
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            d = asdict(r)
            w.writerow({k: d.get(k) for k in fieldnames})


def export_impact_pack(
    folder: str | Path,
    baseline_rows: list[ActivityRow],
    scenario_rows: list[ActivityRow],
    changes: ChangeSummary,
    project_duration_baseline: int | None,
    project_duration_scenario: int | None,
) -> Path:
    """
    Writes a small export bundle:
      - baseline_metrics.csv
      - scenario_metrics.csv
      - changes.csv
      - summary.txt

    Returns the folder path.
    """
    out_dir = Path(folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    export_activity_metrics_csv(out_dir / "baseline_metrics.csv", baseline_rows)
    export_activity_metrics_csv(out_dir / "scenario_metrics.csv", scenario_rows)

    # changes.csv
    with (out_dir / "changes.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["change_type", "id_or_edge", "from", "to"])
        for aid, bd, sd in changes.changed_durations:
            w.writerow(["duration_change", aid, bd, sd])
        for r in changes.added_relationships:
            w.writerow(["relationship_added", f"{r.pred_id}->{r.succ_id}({r.rel_type.value})", "", r.lag_days])
        for r in changes.removed_relationships:
            w.writerow(["relationship_removed", f"{r.pred_id}->{r.succ_id}({r.rel_type.value})", r.lag_days, ""])

    # summary.txt
    lines = []
    lines.append("FieldFlow Impact Pack")
    lines.append("")
    lines.append(f"Baseline project duration: {project_duration_baseline if project_duration_baseline is not None else '—'}")
    lines.append(f"Scenario project duration:  {project_duration_scenario if project_duration_scenario is not None else '—'}")
    if project_duration_baseline is not None and project_duration_scenario is not None:
        lines.append(f"Delta (scenario - baseline): {project_duration_scenario - project_duration_baseline} days")
    lines.append("")
    lines.append("Changed durations:")
    if changes.changed_durations:
        for aid, bd, sd in changes.changed_durations:
            lines.append(f"  - {aid}: {bd} → {sd} days")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Added relationships:")
    if changes.added_relationships:
        for r in changes.added_relationships:
            lines.append(f"  + {r.pred_id} -> {r.succ_id} {r.rel_type.value} lag={r.lag_days}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Removed relationships:")
    if changes.removed_relationships:
        for r in changes.removed_relationships:
            lines.append(f"  - {r.pred_id} -> {r.succ_id} {r.rel_type.value} lag={r.lag_days}")
    else:
        lines.append("  (none)")
    lines.append("")

    (out_dir / "summary.txt").write_text("\n".join(lines), encoding="utf-8")

    return out_dir