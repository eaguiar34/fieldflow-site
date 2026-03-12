from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class WorkPackage:
    """
    Work package cost model.

    pricing_mode:
      - "unit": use unit_cost directly
      - "crew": derive unit cost from crew/equipment production + material (+ waste)

    curve_style (cost distribution across ES..EF weeks):
      - "linear": uniform
      - "front": front-loaded
      - "back": back-loaded
      - "bell": bell curve (mid-peaked)

    Optional library references:
      - crew_profile_id: look up crew_cost_per_day if crew_cost_per_day is None
      - equip_profile_id: look up equipment_cost_per_day if equipment_cost_per_day is None
    """
    id: str
    name: str
    qty: float
    unit: str
    unit_cost: float
    linked_activity_ids: str = ""

    # pricing
    pricing_mode: str = "unit"  # "unit" | "crew"
    production_units_per_day: Optional[float] = None
    crew_cost_per_day: Optional[float] = None
    equipment_cost_per_day: Optional[float] = None
    material_unit_cost: Optional[float] = None
    waste_factor: float = 0.0

    # forecast behavior
    curve_style: str = "linear"  # "linear" | "front" | "back" | "bell"

    # references into rate library (global)
    crew_profile_id: str = ""
    equip_profile_id: str = ""

    def derived_unit_cost(self) -> float:
        if (self.pricing_mode or "unit").lower() != "crew":
            return float(self.unit_cost or 0.0)

        prod = float(self.production_units_per_day or 0.0)
        if prod <= 0.0:
            return float(self.unit_cost or 0.0)

        crew = float(self.crew_cost_per_day or 0.0)
        equip = float(self.equipment_cost_per_day or 0.0)
        mat = float(self.material_unit_cost or 0.0)

        base = (crew + equip) / prod
        unit = base + mat

        wf = float(self.waste_factor or 0.0)
        if wf < 0:
            wf = 0.0
        if wf > 1.0:
            wf = 1.0

        return unit * (1.0 + wf)

    def total_cost(self) -> float:
        q = float(self.qty or 0.0)
        return q * self.derived_unit_cost()


@dataclass
class RFI:
    id: str
    title: str
    status: str = "Open"
    created: Optional[date] = None
    due: Optional[date] = None
    answered: Optional[date] = None
    linked_activity_ids: str = ""
    impact_days: int = 0


@dataclass
class Submittal:
    id: str
    spec_section: str
    status: str = "Required"
    required_by_activity_id: str = ""
    lead_time_days: int = 0
    submit_date: Optional[date] = None
    approve_date: Optional[date] = None