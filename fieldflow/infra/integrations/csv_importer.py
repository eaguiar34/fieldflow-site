from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportedActivity:
    id: str
    name: str
    duration_days: int


def import_activities_csv(path: str | Path) -> list[ImportedActivity]:
    """
    Import activities from a CSV.

    Expected columns (header names, case-insensitive):
      - id (or activity_id)
      - name (or activity_name)
      - duration (or duration_days)

    Example CSV:
      id,name,duration
      A001,Mobilize,5
      A002,Excavation,10
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    with p.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row.")

        # Build a case-insensitive field map
        fields = {h.strip().lower(): h for h in reader.fieldnames}

        def pick(*candidates: str) -> str | None:
            for c in candidates:
                if c in fields:
                    return fields[c]
            return None

        id_col = pick("id", "activity_id")
        name_col = pick("name", "activity_name")
        dur_col = pick("duration", "duration_days")

        missing = [n for n, c in [("id", id_col), ("name", name_col), ("duration", dur_col)] if c is None]
        if missing:
            raise ValueError(
                "CSV missing required columns: "
                + ", ".join(missing)
                + ". Expected headers like: id,name,duration"
            )

        out: list[ImportedActivity] = []
        for i, row in enumerate(reader, start=2):  # start=2 because header is row 1
            raw_id = (row.get(id_col) or "").strip()
            raw_name = (row.get(name_col) or "").strip()
            raw_dur = (row.get(dur_col) or "").strip()

            if not raw_id:
                raise ValueError(f"Row {i}: missing activity id.")
            if not raw_name:
                raise ValueError(f"Row {i}: missing activity name.")
            try:
                dur = int(float(raw_dur))
            except Exception:
                raise ValueError(f"Row {i}: invalid duration '{raw_dur}'. Must be a number.")

            out.append(ImportedActivity(raw_id, raw_name, dur))

    return out