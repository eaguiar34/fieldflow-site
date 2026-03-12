from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

from PySide6.QtCore import QSettings


@dataclass
class CrewProfile:
    id: str
    name: str
    cost_per_day: float


@dataclass
class EquipmentProfile:
    id: str
    name: str
    cost_per_day: float


class RateLibraryStore:
    """
    Global (not per-project) rate library stored in QSettings.
    """
    def __init__(self) -> None:
        self.q = QSettings("FieldFlow", "FieldFlow")
        self.key = "ui/rate_library_json"

    def load(self) -> Tuple[List[CrewProfile], List[EquipmentProfile]]:
        raw = self.q.value(self.key, "")
        if not raw:
            return [], []
        if not isinstance(raw, str):
            raw = str(raw)
        try:
            data = json.loads(raw)
        except Exception:
            return [], []

        crews = [
            CrewProfile(
                id=str(x.get("id", "")),
                name=str(x.get("name", "")),
                cost_per_day=float(x.get("cost_per_day", 0.0) or 0.0),
            )
            for x in (data.get("crews", []) or [])
        ]
        equips = [
            EquipmentProfile(
                id=str(x.get("id", "")),
                name=str(x.get("name", "")),
                cost_per_day=float(x.get("cost_per_day", 0.0) or 0.0),
            )
            for x in (data.get("equipment", []) or [])
        ]
        return crews, equips

    def save(self, crews: List[CrewProfile], equipment: List[EquipmentProfile]) -> None:
        payload = {
            "crews": [asdict(c) for c in (crews or [])],
            "equipment": [asdict(e) for e in (equipment or [])],
        }
        self.q.setValue(self.key, json.dumps(payload, indent=2))

    def crew_map(self) -> Dict[str, CrewProfile]:
        crews, _ = self.load()
        return {c.id: c for c in crews if c.id}

    def equip_map(self) -> Dict[str, EquipmentProfile]:
        _, eq = self.load()
        return {e.id: e for e in eq if e.id}