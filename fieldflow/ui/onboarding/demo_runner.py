from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QApplication

from fieldflow.app.controls_store import ControlsStore
from fieldflow.app.controls_models import WorkPackage, RFI, Submittal
from fieldflow.app.controls_impacts import build_controls_impact_scenario
from fieldflow.ui.shell.app_context import AppContext


class DemoProgressDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Setting up Walkthrough Demo…")
        self.setModal(True)
        self.resize(520, 140)

        layout = QVBoxLayout(self)
        self.lbl = QLabel("Preparing demo…")
        self.lbl.setWordWrap(True)
        layout.addWidget(self.lbl)

    def set_text(self, s: str) -> None:
        self.lbl.setText(s)
        QApplication.processEvents()


class DemoRunner(QObject):
    finished = Signal(bool, str)  # ok, message

    def __init__(self, ctx: AppContext, shell) -> None:
        super().__init__(shell)
        self.ctx = ctx
        self.shell = shell
        self.dlg = DemoProgressDialog(parent=shell)

    def run(self) -> None:
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()
        QTimer.singleShot(50, self._step1_load_example_data)

    def _step1_load_example_data(self) -> None:
        try:
            self.dlg.set_text("Step 1/6 — Loading example activities, logic, and controls…")

            base = Path(__file__).resolve().parent / "sample_data"
            act_csv = base / "activities_example.csv"
            log_csv = base / "logic_example.csv"
            ctl_json = base / "controls_seed.json"

            if not (act_csv.exists() and log_csv.exists() and ctl_json.exists()):
                raise FileNotFoundError(
                    "Missing onboarding sample_data.\n"
                    f"Expected:\n  {act_csv}\n  {log_csv}\n  {ctl_json}"
                )

            self.ctx.import_activities(act_csv)
            self.ctx.import_logic(log_csv)

            data = json.loads(ctl_json.read_text(encoding="utf-8"))
            store = ControlsStore()

            def parse_date(s):
                if not s:
                    return None
                return date.fromisoformat(s)

            wps = [
                WorkPackage(
                    id=str(x.get("id", "")),
                    name=str(x.get("name", "")),
                    qty=float(x.get("qty", 0.0)),
                    unit=str(x.get("unit", "")),
                    unit_cost=float(x.get("unit_cost", 0.0)),
                    linked_activity_ids=str(x.get("linked_activity_ids", "")),
                )
                for x in data.get("work_packages", [])
            ]
            rfis = [
                RFI(
                    id=str(x.get("id", "")),
                    title=str(x.get("title", "")),
                    status=str(x.get("status", "Open")),
                    created=parse_date(x.get("created")),
                    due=parse_date(x.get("due")),
                    answered=parse_date(x.get("answered")),
                    linked_activity_ids=str(x.get("linked_activity_ids", "")),
                    impact_days=int(x.get("impact_days", 0) or 0),
                )
                for x in data.get("rfis", [])
            ]
            subs = [
                Submittal(
                    id=str(x.get("id", "")),
                    spec_section=str(x.get("spec_section", "")),
                    status=str(x.get("status", "Required")),
                    required_by_activity_id=str(x.get("required_by_activity_id", "")),
                    lead_time_days=int(x.get("lead_time_days", 0) or 0),
                    submit_date=parse_date(x.get("submit_date")),
                    approve_date=parse_date(x.get("approve_date")),
                )
                for x in data.get("submittals", [])
            ]
            store.save(self.ctx.project_key, wps, rfis, subs)

            if hasattr(self.shell, "_reload_pages"):
                try:
                    self.shell._reload_pages()
                except Exception:
                    pass

            if hasattr(self.shell, "set_page"):
                try:
                    self.shell.set_page("schedule")
                except Exception:
                    pass

            QTimer.singleShot(80, self._step2_compute_both)
        except Exception as e:
            self._fail(f"Demo setup failed during load:\n{e}")

    def _step2_compute_both(self) -> None:
        try:
            self.dlg.set_text("Step 2/6 — Computing schedule (Baseline + Active)…")
            if hasattr(self.shell, "compute_both_safe"):
                self.shell.compute_both_safe()
            QTimer.singleShot(120, self._step3_build_impact_scenario)
        except Exception as e:
            self._fail(f"Demo setup failed during compute:\n{e}")

    def _step3_build_impact_scenario(self) -> None:
        try:
            self.dlg.set_text("Step 3/6 — Building Impact Scenario from RFIs/Submittals…")

            store = ControlsStore()
            _wps, rfis, subs = store.load(self.ctx.project_key)

            scenario_name = "Walkthrough Impacts"
            if scenario_name not in {s.name for s in self.ctx.project.scenarios}:
                self.ctx.controller.create_scenario_from_baseline(self.ctx.project, scenario_name)

            impacted, _warnings = build_controls_impact_scenario(
                baseline=self.ctx.project.baseline,
                rfis=rfis,
                submittals=subs,
                calendar=self.ctx.calendar,
                today=date.today(),
            )
            impacted.name = scenario_name

            found = False
            for i, s in enumerate(self.ctx.project.scenarios):
                if s.name == scenario_name:
                    self.ctx.project.scenarios[i] = impacted
                    found = True
                    break
            if not found:
                self.ctx.project.scenarios.append(impacted)

            self.ctx.controller.save_scenario_from_state(scenario_name, impacted)
            self.ctx.set_active_scenario(scenario_name)

            QTimer.singleShot(80, self._step4_compute_both_again)
        except Exception as e:
            self._fail(f"Demo setup failed during impact scenario build:\n{e}")

    def _step4_compute_both_again(self) -> None:
        try:
            self.dlg.set_text("Step 4/6 — Recomputing schedule (Baseline vs Impacts)…")
            if hasattr(self.shell, "compute_both_safe"):
                self.shell.compute_both_safe()
            QTimer.singleShot(120, self._step5_open_scenarios)
        except Exception as e:
            self._fail(f"Demo setup failed during recompute:\n{e}")

    def _step5_open_scenarios(self) -> None:
        try:
            self.dlg.set_text("Step 5/6 — Opening Scenarios and selecting top delay driver…")
            if hasattr(self.shell, "open_scenarios_and_select_top_driver"):
                self.shell.open_scenarios_and_select_top_driver()
            QTimer.singleShot(120, self._step6_launch_tour)
        except Exception as e:
            self._fail(f"Demo setup failed opening scenarios:\n{e}")

    def _step6_launch_tour(self) -> None:
        try:
            self.dlg.set_text("Step 6/6 — Launching guided tour…")
            self.dlg.close()

            from fieldflow.ui.onboarding.tour import GuidedTour
            GuidedTour(self.shell).start()

            self.finished.emit(True, "Walkthrough demo ready.")
        except Exception as e:
            self._fail(f"Demo setup failed during tour launch:\n{e}")

    def _fail(self, msg: str) -> None:
        try:
            self.dlg.close()
        except Exception:
            pass
        self.finished.emit(False, msg)