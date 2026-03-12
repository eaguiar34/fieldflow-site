from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportedRelationship:
    pred_id: str
    succ_id: str
    rel_type: str  # FS/SS/FF/SF
    lag_days: int


def import_logic_csv(path: str | Path) -> list[ImportedRelationship]:
    """
    Import relationships from a CSV.

    Required headers (case-insensitive):
      pred_id, succ_id

    Optional:
      type  (FS/SS/FF/SF) default FS
      lag   (integer) default 0

    Example:
      pred_id,succ_id,type,lag
      A100,A110,FS,0
      A110,A120,SS,2
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    with p.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row.")

        fields = {h.strip().lower(): h for h in reader.fieldnames}

        pred_col = fields.get("pred_id") or fields.get("pred") or fields.get("predecessor")
        succ_col = fields.get("succ_id") or fields.get("succ") or fields.get("successor")
        type_col = fields.get("type") or fields.get("rel_type") or fields.get("relationship_type")
        lag_col = fields.get("lag") or fields.get("lag_days")

        if not pred_col or not succ_col:
            raise ValueError("Logic CSV must contain headers like: pred_id,succ_id (type,lag optional)")

        out: list[ImportedRelationship] = []
        for i, row in enumerate(reader, start=2):
            pred = (row.get(pred_col) or "").strip()
            succ = (row.get(succ_col) or "").strip()
            if not pred or not succ:
                raise ValueError(f"Row {i}: pred_id and succ_id are required.")

            rtype = "FS"
            if type_col:
                rtype = ((row.get(type_col) or "FS").strip() or "FS").upper()
            if rtype not in ("FS", "SS", "FF", "SF"):
                raise ValueError(f"Row {i}: invalid type '{rtype}'. Use FS/SS/FF/SF.")

            lag = 0
            if lag_col:
                raw = (row.get(lag_col) or "0").strip()
                try:
                    lag = int(float(raw))
                except Exception:
                    raise ValueError(f"Row {i}: invalid lag '{raw}'. Must be a number.")

            out.append(ImportedRelationship(pred, succ, rtype, lag))

    return out