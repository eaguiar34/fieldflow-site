from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from typing import List, Tuple, Optional

from PySide6.QtCore import QSettings

from fieldflow.app.controls_models import WorkPackage, RFI, Submittal


def _d_to_iso(d: Optional[date]) -> Optional[str]:
    return None if d is None else d.isoformat()


def _iso_to_d(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s))
    except Exception:
        return None


class ControlsStore:
    """
    Stores controls (Work Packages / RFIs / Submittals) in QSettings as JSON.

    Key is namespaced by project_key, so each project has its own controls.
    """
    def __init__(self) -> None:
        self.q = QSettings("FieldFlow", "FieldFlow")

    def _key(self, project_key: str) -> str:
        return f"projects/{project_key}/controls/json"

    def load(self, project_key: str) -> Tuple[List[WorkPackage], List[RFI], List[Submittal]]:
        raw = self.q.value(self._key(project_key), "")
        if not raw:
            return [], [], []

        if not isinstance(raw, str):
            raw = str(raw)

        try:
            data = json.loads(raw)
        except Exception:
            return [], [], []

        wps: List[WorkPackage] = []
        for x in data.get("work_packages", []) or []:
            wps.append(
                WorkPackage(
                    id=str(x.get("id", "")),
                    name=str(x.get("name", "")),
                    qty=float(x.get("qty", 0.0) or 0.0),
                    unit=str(x.get("unit", "")),
                    unit_cost=float(x.get("unit_cost", 0.0) or 0.0),
                    linked_activity_ids=str(x.get("linked_activity_ids", "")),

                    pricing_mode=str(x.get("pricing_mode", "unit") or "unit"),
                    production_units_per_day=(
                        None if x.get("production_units_per_day", None) in (None, "")
                        else float(x.get("production_units_per_day"))
                    ),
                    crew_cost_per_day=(
                        None if x.get("crew_cost_per_day", None) in (None, "")
                        else float(x.get("crew_cost_per_day"))
                    ),
                    equipment_cost_per_day=(
                        None if x.get("equipment_cost_per_day", None) in (None, "")
                        else float(x.get("equipment_cost_per_day"))
                    ),
                    material_unit_cost=(
                        None if x.get("material_unit_cost", None) in (None, "")
                        else float(x.get("material_unit_cost"))
                    ),
                    waste_factor=float(x.get("waste_factor", 0.0) or 0.0),

                    curve_style=str(x.get("curve_style", "linear") or "linear"),
                    crew_profile_id=str(x.get("crew_profile_id", "") or ""),
                    equip_profile_id=str(x.get("equip_profile_id", "") or ""),
                )
            )

        rfis: List[RFI] = []
        for x in data.get("rfis", []) or []:
            rfis.append(
                RFI(
                    id=str(x.get("id", "")),
                    title=str(x.get("title", "")),
                    status=str(x.get("status", "Open")),
                    created=_iso_to_d(x.get("created")),
                    due=_iso_to_d(x.get("due")),
                    answered=_iso_to_d(x.get("answered")),
                    linked_activity_ids=str(x.get("linked_activity_ids", "")),
                    impact_days=int(x.get("impact_days", 0) or 0),
                )
            )

        subs: List[Submittal] = []
        for x in data.get("submittals", []) or []:
            subs.append(
                Submittal(
                    id=str(x.get("id", "")),
                    spec_section=str(x.get("spec_section", "")),
                    status=str(x.get("status", "Required")),
                    required_by_activity_id=str(x.get("required_by_activity_id", "")),
                    lead_time_days=int(x.get("lead_time_days", 0) or 0),
                    submit_date=_iso_to_d(x.get("submit_date")),
                    approve_date=_iso_to_d(x.get("approve_date")),
                )
            )

        return wps, rfis, subs

    def save(self, project_key: str, work_packages: List[WorkPackage], rfis: List[RFI], submittals: List[Submittal]) -> None:
        def wp_dict(wp: WorkPackage) -> dict:
            d = asdict(wp)
            d["qty"] = float(wp.qty or 0.0)
            d["unit_cost"] = float(wp.unit_cost or 0.0)
            d["waste_factor"] = float(wp.waste_factor or 0.0)
            d["curve_style"] = str(wp.curve_style or "linear")
            d["crew_profile_id"] = str(wp.crew_profile_id or "")
            d["equip_profile_id"] = str(wp.equip_profile_id or "")
            return d

        def rfi_dict(r: RFI) -> dict:
            return {
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "created": _d_to_iso(r.created),
                "due": _d_to_iso(r.due),
                "answered": _d_to_iso(r.answered),
                "linked_activity_ids": r.linked_activity_ids,
                "impact_days": int(r.impact_days or 0),
            }

        def sub_dict(s: Submittal) -> dict:
            return {
                "id": s.id,
                "spec_section": s.spec_section,
                "status": s.status,
                "required_by_activity_id": s.required_by_activity_id,
                "lead_time_days": int(s.lead_time_days or 0),
                "submit_date": _d_to_iso(s.submit_date),
                "approve_date": _d_to_iso(s.approve_date),
            }

        payload = {
            "work_packages": [wp_dict(wp) for wp in (work_packages or [])],
            "rfis": [rfi_dict(r) for r in (rfis or [])],
            "submittals": [sub_dict(s) for s in (submittals or [])],
        }
        self.q.setValue(self._key(project_key), json.dumps(payload, indent=2))