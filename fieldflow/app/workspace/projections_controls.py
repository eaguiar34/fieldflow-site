from __future__ import annotations

"""
Controls projections (materialized views) from the event stream.

First projection: Work Packages.

This projection is intentionally simple:
  - We keep "latest wins" per WorkPackage.id using event timestamps.
  - Output: cache/projections/controls_work_packages.json
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional, Tuple

from fieldflow.app.workspace.event_log import Event


def _event_key(e: Event) -> str:
    return f"{e.ts_utc}|{e.actor}|{e.entity}|{e.entity_id}|{e.op}"


class ControlsWorkPackagesProjection:
    def __init__(self, projections_dir: Path) -> None:
        self.projections_dir = Path(projections_dir)
        self.path = self.projections_dir / "controls_work_packages.json"

        # wp_id -> (ts_utc, wp_dict)
        self._wps: Dict[str, Tuple[str, dict]] = {}

        self._loaded = False

    def _load_if_needed(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            items = d.get("items", []) or []
            for it in items:
                wp_id = str(it.get("id", "") or "").strip()
                ts = str(it.get("_ts_utc", "") or "")
                if wp_id:
                    self._wps[wp_id] = (ts, dict(it))
        except Exception:
            # If cache corrupt, we silently rebuild from events over time.
            self._wps = {}

    def _save(self) -> None:
        out_items = []
        for wp_id, (ts, wp) in self._wps.items():
            wp2 = dict(wp)
            wp2["id"] = wp_id
            wp2["_ts_utc"] = ts
            out_items.append(wp2)
        out = {
            "format": "fieldflow_projection_controls_work_packages_v1",
            "items": sorted(out_items, key=lambda x: x.get("id", "")),
        }
        self.projections_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    def apply(self, e: Event) -> None:
        self._load_if_needed()

        # Two supported event shapes:
        # 1) bulk save: entity="controls", op="save_work_packages", payload={"items":[{...wp...}, ...]}
        if (e.entity == "controls") and (e.op == "save_work_packages"):
            items = (e.payload or {}).get("items", []) or []
            changed = False
            for it in items:
                wp_id = str(it.get("id", "") or "").strip()
                if not wp_id:
                    continue
                prev = self._wps.get(wp_id)
                if prev is None or str(e.ts_utc) >= str(prev[0]):
                    self._wps[wp_id] = (str(e.ts_utc), dict(it))
                    changed = True
            if changed:
                self._save()
            return

        # 2) per-item ops
        if e.entity in ("work_packages", "controls.work_packages"):
            wp_id = str(e.payload.get("id", "") or e.entity_id or "").strip()
            if not wp_id:
                return

            if e.op in ("upsert", "save", "update"):
                wp = dict(e.payload or {})
                prev = self._wps.get(wp_id)
                if prev is None or str(e.ts_utc) >= str(prev[0]):
                    self._wps[wp_id] = (str(e.ts_utc), wp)
                    self._save()
                return

            if e.op in ("delete", "remove"):
                if wp_id in self._wps:
                    del self._wps[wp_id]
                    self._save()
                return

    def load_items(self) -> list[dict]:
        self._load_if_needed()
        return [dict(v[1]) for v in self._wps.values()]