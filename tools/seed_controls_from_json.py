# tools/seed_controls_from_json.py
# Run this from Spyder or terminal to load example controls into your current project_key.
#
# Usage (Spyder):
#   %runfile C:/Users/Emiliano/Projects/FieldFlow/tools/seed_controls_from_json.py --wdir
#
# It will print your project_key and then write controls into QSettings under that key.

from pathlib import Path
import json

from fieldflow.ui.shell.app_context import AppContext
from fieldflow.app.controls_store import ControlsStore

HERE = Path(__file__).resolve().parent
seed_path = HERE / "example_data" / "controls_seed.json"

ctx = AppContext()
print("Project key:", ctx.project_key)

data = json.loads(seed_path.read_text(encoding="utf-8"))
store = ControlsStore()

store.save(
    ctx.project_key,
    work_packages=[
        # ControlsStore accepts dataclasses; it will coerce via its save() helpers if you pass proper objects.
        # Easiest: reuse load() format by loading then saving through store.save with actual model instances.
    ],
    rfis=[],
    submittals=[],
)

# The above is intentionally left blank because ControlsStore.save expects model instances.
# Instead, do the robust approach below using the same constructors ControlsStore.load uses:

from fieldflow.app.controls_models import WorkPackage, RFI, Submittal
from datetime import date

def parse_date(s):
    if not s:
        return None
    return date.fromisoformat(s)

wps = []
for x in data.get("work_packages", []):
    wps.append(WorkPackage(
        id=str(x.get("id","")),
        name=str(x.get("name","")),
        qty=float(x.get("qty",0.0)),
        unit=str(x.get("unit","")),
        unit_cost=float(x.get("unit_cost",0.0)),
        linked_activity_ids=str(x.get("linked_activity_ids","")),
    ))

rfis = []
for x in data.get("rfis", []):
    rfis.append(RFI(
        id=str(x.get("id","")),
        title=str(x.get("title","")),
        status=str(x.get("status","Open")),
        created=parse_date(x.get("created")),
        due=parse_date(x.get("due")),
        answered=parse_date(x.get("answered")),
        linked_activity_ids=str(x.get("linked_activity_ids","")),
        impact_days=int(x.get("impact_days",0) or 0),
    ))

subs = []
for x in data.get("submittals", []):
    subs.append(Submittal(
        id=str(x.get("id","")),
        spec_section=str(x.get("spec_section","")),
        status=str(x.get("status","Required")),
        required_by_activity_id=str(x.get("required_by_activity_id","")),
        lead_time_days=int(x.get("lead_time_days",0) or 0),
        submit_date=parse_date(x.get("submit_date")),
        approve_date=parse_date(x.get("approve_date")),
    ))

store.save(ctx.project_key, wps, rfis, subs)
print(f"Seeded controls into QSettings for project_key={ctx.project_key}")
print("Open FieldFlow and go to Controls / RFIs / Submittals pages, then Tools -> Compute Both and Scenarios -> Build Impact Scenario.")
