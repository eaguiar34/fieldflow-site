from __future__ import annotations

from datetime import date
from typing import Any, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
)

from fieldflow.app.controls_impacts import (
    build_controls_impact_scenario_with_provenance,
    controls_provenance_entries_for_activity,
)
from fieldflow.app.controls_store import ControlsStore
from fieldflow.ui.shell.app_context import AppContext


class ScenariosPage(QWidget):
    """Scenario management + baseline-vs-active analysis + provenance.

    Adds a lightweight "Why (Controls)" panel:
    - Click a row in Deltas or Delay Drivers to see which RFIs/Submittals affect that activity.

    This is computed on the fly from ControlsStore (no extra persistence needed).
    """

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._controls_store = ControlsStore()

        layout = QVBoxLayout(self)

        title = QLabel("Scenarios: Baseline vs Active (Analysis)")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        # ---- buttons ----
        btns = QHBoxLayout()
        self.btn_new = QPushButton("New Scenario…")
        self.btn_del = QPushButton("Delete Scenario…")
        self.btn_build_impacts = QPushButton("Build Impact Scenario…")
        self.btn_rebuild_impacts = QPushButton("Rebuild Impact Scenario")
        btns.addWidget(self.btn_new)
        btns.addWidget(self.btn_del)
        btns.addSpacing(12)
        btns.addWidget(self.btn_build_impacts)
        btns.addWidget(self.btn_rebuild_impacts)

        self.chk_only_changes = QCheckBox("Show only changed")
        self.chk_only_changes.setChecked(True)
        self.chk_only_changes.stateChanged.connect(lambda _: self.refresh_results())
        btns.addSpacing(12)
        btns.addWidget(self.chk_only_changes)

        btns.addStretch(1)
        layout.addLayout(btns)

        info = QLabel(
            "Workflow: (1) Build/choose scenario → (2) Tools → Compute Both → (3) analyze deltas + delay drivers."
        )
        info.setStyleSheet("color: #666;")
        layout.addWidget(info)

        # ---- tabs ----
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # Deltas table
        self.table = QTableWidget()
        self.table.setColumnCount(17)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Name",
                "B.ES",
                "A.ES",
                "ΔES",
                "B.EF",
                "A.EF",
                "ΔEF",
                "B.LS",
                "A.LS",
                "ΔLS",
                "B.LF",
                "A.LF",
                "ΔLF",
                "B.TF",
                "A.TF",
                "ΔTF",
            ]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        self.tabs.addTab(self.table, "Deltas")

        # Delay drivers
        self.drivers = QTableWidget()
        self.drivers.setColumnCount(9)
        self.drivers.setHorizontalHeaderLabels(
            [
                "ID",
                "Name",
                "ΔLF",
                "ΔEF",
                "ΔTF",
                "B.LF",
                "A.LF",
                "B.EF",
                "A.EF",
            ]
        )
        self.drivers.setEditTriggers(QTableWidget.NoEditTriggers)
        self.drivers.setSelectionBehavior(QTableWidget.SelectRows)
        self.drivers.setSortingEnabled(True)
        self.tabs.addTab(self.drivers, "Delay Drivers")

        # ---- provenance panel ----
        why_box = QGroupBox("Why (Controls)")
        v = QVBoxLayout(why_box)
        self.lbl_why_hint = QLabel("Click an item to jump to the underlying RFI/Submittal.")
        self.lbl_why_hint.setWordWrap(True)
        self.lbl_why_hint.setStyleSheet("color: #666;")
        v.addWidget(self.lbl_why_hint)

        self.lst_why = QListWidget()
        self.lst_why.itemActivated.connect(self._on_why_activated)
        v.addWidget(self.lst_why)
        layout.addWidget(why_box)

        self.footer = QLabel("")
        self.footer.setStyleSheet("color: #666; padding: 4px;")
        layout.addWidget(self.footer)

        # wiring
        self.btn_new.clicked.connect(self._new_scenario)
        self.btn_del.clicked.connect(self._delete_scenario)
        self.btn_build_impacts.clicked.connect(self._build_impact_scenario)
        self.btn_rebuild_impacts.clicked.connect(self._rebuild_impact_scenario)

        ctx.signals.schedule_compared.connect(self.refresh_results)
        ctx.signals.active_scenario_changed.connect(lambda _: self._clear())
        ctx.signals.project_loaded.connect(self._clear)

        # selection → provenance
        if self.table.selectionModel() is not None:
            self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_provenance_from_table(self.table))
        if self.drivers.selectionModel() is not None:
            self.drivers.selectionModel().selectionChanged.connect(lambda *_: self._update_provenance_from_table(self.drivers))

        self._clear()

    # -------------------- utils --------------------
    def _clear(self) -> None:
        self.table.setRowCount(0)
        self.drivers.setRowCount(0)
        self.footer.setText("No comparison yet. Tools → Compute Both (Baseline + Active).")
        self.lst_why.clear()
        self.lst_why.addItem(QListWidgetItem("Select an activity row to see drivers."))

    def _idx_to_date(self, idx: Optional[int]) -> str:
        if idx is None:
            return "—"
        try:
            return str(self.ctx.calendar.add_working_days(self.ctx.project_start, int(idx)))
        except Exception:
            return str(idx)

    def _int(self, obj: Any, *names: str) -> Optional[int]:
        for n in names:
            v = getattr(obj, n, None)
            if v is None:
                continue
            try:
                return int(v)
            except Exception:
                continue
        return None

    def _delta_str(self, b: Optional[int], a: Optional[int]) -> str:
        if b is None or a is None:
            return "—"
        return f"{(a - b):+d}"

    def _unique_scenario_name(self, base: str) -> str:
        existing = {"Baseline"} | {s.name for s in self.ctx.project.scenarios}
        if base not in existing:
            return base
        i = 2
        while f"{base} {i}" in existing:
            i += 1
        return f"{base} {i}"

    def _last_impact_scenario_key(self) -> str:
        return f"{self.ctx.settings_prefix()}/impacts/last_scenario"

    def _get_last_impact_scenario_name(self) -> str:
        try:
            v = self.ctx.qsettings.value(self._last_impact_scenario_key(), "")
            return str(v or "").strip()
        except Exception:
            return ""

    def _set_last_impact_scenario_name(self, name: str) -> None:
        try:
            self.ctx.qsettings.setValue(self._last_impact_scenario_key(), str(name))
        except Exception:
            pass

    def _load_controls(self):
        try:
            _wps, rfis, subs = self._controls_store.load(self.ctx.project_key)
            return rfis, subs
        except Exception:
            return [], []

    def _update_provenance_from_table(self, table: QTableWidget) -> None:
        items = table.selectedItems()
        if not items:
            return
        r = items[0].row()
        it = table.item(r, 0)
        if it is None:
            return
        aid = it.text().strip()
        if not aid:
            return

        rfis, subs = self._load_controls()
        self.lst_why.clear()
        entries = controls_provenance_entries_for_activity(
            rfis=rfis,
            submittals=subs,
            activity_id=aid,
            today=date.today(),
        )
        if not entries:
            self.lst_why.addItem(QListWidgetItem("No RFI/Submittal drivers found for this activity."))
            return

        for e in entries:
            label = str(e.get("label", "")) or "(unknown)"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, e)
            self.lst_why.addItem(it)

    def _on_why_activated(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict):
            return
        page = str(data.get("page", ""))
        select_id = data.get("select_id")
        if not page or not select_id:
            return
        if hasattr(self.ctx.signals, "request_navigate"):
            try:
                self.ctx.signals.request_navigate.emit(page, {"select_id": str(select_id)})
            except Exception:
                pass

    # -------------------- analysis --------------------
    def refresh_results(self) -> None:
        base = self.ctx.results.baseline
        active = self.ctx.results.active
        active_name = self.ctx.results.compared_active_name

        if base is None or active is None or not active_name or active_name == "Baseline":
            self._clear()
            return

        base_m = getattr(base, "metrics_by_id", None)
        act_m = getattr(active, "metrics_by_id", None)
        if not isinstance(base_m, dict) or not isinstance(act_m, dict):
            self._clear()
            self.footer.setText("Results exist but metrics_by_id is missing/unrecognized.")
            return

        common = sorted(set(base_m.keys()) & set(act_m.keys()))
        only_changes = self.chk_only_changes.isChecked()

        rows: List[Tuple[Any, ...]] = []
        driver_rows: List[Tuple[Any, ...]] = []

        for aid in common:
            bm = base_m[aid]
            am = act_m[aid]

            bes = self._int(bm, "es", "ES")
            aes = self._int(am, "es", "ES")
            bef = self._int(bm, "ef", "EF")
            aef = self._int(am, "ef", "EF")
            bls = self._int(bm, "ls", "LS")
            als = self._int(am, "ls", "LS")
            blf = self._int(bm, "lf", "LF")
            alf = self._int(am, "lf", "LF")
            btf = self._int(bm, "total_float", "tf", "TF")
            atf = self._int(am, "total_float", "tf", "TF")

            if only_changes:
                if (bes == aes) and (bef == aef) and (bls == als) and (blf == alf) and (btf == atf):
                    continue

            name = getattr(am, "name", None) or getattr(bm, "name", None) or ""

            rows.append(
                (
                    aid,
                    name,
                    self._idx_to_date(bes),
                    self._idx_to_date(aes),
                    self._delta_str(bes, aes),
                    self._idx_to_date(bef),
                    self._idx_to_date(aef),
                    self._delta_str(bef, aef),
                    self._idx_to_date(bls),
                    self._idx_to_date(als),
                    self._delta_str(bls, als),
                    self._idx_to_date(blf),
                    self._idx_to_date(alf),
                    self._delta_str(blf, alf),
                    "—" if btf is None else str(btf),
                    "—" if atf is None else str(atf),
                    self._delta_str(btf, atf),
                )
            )

            dlf = None if (blf is None or alf is None) else (alf - blf)
            defv = None if (bef is None or aef is None) else (aef - bef)
            dtf = None if (btf is None or atf is None) else (atf - btf)
            driver_rows.append(
                (
                    aid,
                    name,
                    "—" if dlf is None else f"{dlf:+d}",
                    "—" if defv is None else f"{defv:+d}",
                    "—" if dtf is None else f"{dtf:+d}",
                    self._idx_to_date(blf),
                    self._idx_to_date(alf),
                    self._idx_to_date(bef),
                    self._idx_to_date(aef),
                    dlf if dlf is not None else 0,
                    defv if defv is not None else 0,
                )
            )

        # Populate deltas
        self.table.setRowCount(len(rows))
        for r, vals in enumerate(rows):
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
        self.table.resizeColumnsToContents()

        # Delay drivers sort
        driver_rows.sort(key=lambda t: (t[9], t[10]), reverse=True)
        top = driver_rows[:200]

        self.drivers.setRowCount(len(top))
        for r, t in enumerate(top):
            vals = t[:9]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.drivers.setItem(r, c, it)
        self.drivers.resizeColumnsToContents()

        self.footer.setText(f"Compared {len(rows)} activities: Baseline vs {active_name}. Δ values are WORKING DAYS.")

        # update provenance for current selection (if any)
        self._update_provenance_from_table(self.table)

    # -------------------- scenario mgmt --------------------
    def _new_scenario(self) -> None:
        name, ok = QInputDialog.getText(self, "New Scenario", "Scenario name:")
        if not ok or not name.strip():
            return
        try:
            self.ctx.controller.create_scenario_from_baseline(self.ctx.project, name.strip())
            self.ctx.autosave()
            self.ctx.set_active_scenario(name.strip())
        except Exception as e:
            QMessageBox.warning(self, "Scenario", str(e))

    def _delete_scenario(self) -> None:
        if not self.ctx.project.scenarios:
            QMessageBox.information(self, "Delete Scenario", "No scenarios to delete.")
            return
        choices = [s.name for s in self.ctx.project.scenarios]
        name, ok = QInputDialog.getItem(self, "Delete Scenario", "Choose scenario:", choices, 0, False)
        if not ok or not name:
            return
        try:
            self.ctx.controller.delete_scenario(self.ctx.project, name)
            self.ctx.autosave()
            self.ctx.set_active_scenario("Baseline")
        except Exception as e:
            QMessageBox.warning(self, "Delete Scenario", str(e))

    # -------------------- impact scenario --------------------
    def _build_impact_scenario(self) -> None:
        try:
            _wps, rfis, subs = self._controls_store.load(self.ctx.project_key)
        except Exception as e:
            QMessageBox.warning(self, "Impact Scenario", f"Failed to load controls: {e}")
            return

        if not rfis and not subs:
            QMessageBox.information(self, "Impact Scenario", "No RFIs/Submittals found in Controls.")
            return

        base_name = "Controls Impacts"
        default_name = self._unique_scenario_name(base_name)
        name, ok = QInputDialog.getText(self, "Build Impact Scenario", "Scenario name:", text=default_name)
        if not ok or not name.strip():
            return
        scenario_name = name.strip()

        # Ensure scenario exists
        try:
            if scenario_name not in {s.name for s in self.ctx.project.scenarios}:
                self.ctx.controller.create_scenario_from_baseline(self.ctx.project, scenario_name)
        except Exception as e:
            QMessageBox.warning(self, "Impact Scenario", str(e))
            return

        impacted, warnings, _prov = build_controls_impact_scenario_with_provenance(
            baseline=self.ctx.project.baseline,
            rfis=rfis,
            submittals=subs,
            calendar=self.ctx.calendar,
            today=date.today(),
        )
        impacted.name = scenario_name

        try:
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
            self._set_last_impact_scenario_name(scenario_name)
        except Exception as e:
            QMessageBox.warning(self, "Impact Scenario", f"Failed to save scenario: {e}")
            return

        msg = f"Built scenario '{scenario_name}'.\n\nNext: Tools → Compute Both to compare against Baseline."
        if warnings:
            msg += "\n\nWarnings:\n- " + "\n- ".join(warnings[:10])
            if len(warnings) > 10:
                msg += f"\n- … and {len(warnings) - 10} more"
        QMessageBox.information(self, "Impact Scenario", msg)

    def _rebuild_impact_scenario(self) -> None:
        """Idempotently rebuild the last-built impact scenario.

        If no prior impact scenario is known, we prompt for a target scenario name.
        Rebuild always starts from *Baseline* and re-applies the current controls.
        """
        try:
            _wps, rfis, subs = self._controls_store.load(self.ctx.project_key)
        except Exception as e:
            QMessageBox.warning(self, "Rebuild Impact Scenario", f"Failed to load controls: {e}")
            return

        if not rfis and not subs:
            QMessageBox.information(self, "Rebuild Impact Scenario", "No RFIs/Submittals found in Controls.")
            return

        last = self._get_last_impact_scenario_name()
        if last and last != "Baseline":
            scenario_name = last
        else:
            # fall back: choose an existing scenario or propose a new one
            existing = [s.name for s in self.ctx.project.scenarios]
            default_name = self._unique_scenario_name("Controls Impacts")
            if existing:
                scenario_name, ok = QInputDialog.getItem(
                    self,
                    "Rebuild Impact Scenario",
                    "Rebuild which scenario?",
                    existing,
                    0,
                    False,
                )
                if not ok or not scenario_name:
                    return
            else:
                scenario_name, ok = QInputDialog.getText(
                    self,
                    "Rebuild Impact Scenario",
                    "Scenario name:",
                    text=default_name,
                )
                if not ok or not scenario_name.strip():
                    return
                scenario_name = scenario_name.strip()

        # Ensure scenario exists
        try:
            if scenario_name not in {s.name for s in self.ctx.project.scenarios}:
                self.ctx.controller.create_scenario_from_baseline(self.ctx.project, scenario_name)
        except Exception as e:
            QMessageBox.warning(self, "Rebuild Impact Scenario", str(e))
            return

        impacted, warnings, _prov = build_controls_impact_scenario_with_provenance(
            baseline=self.ctx.project.baseline,
            rfis=rfis,
            submittals=subs,
            calendar=self.ctx.calendar,
            today=date.today(),
        )
        impacted.name = scenario_name

        try:
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
            self._set_last_impact_scenario_name(scenario_name)
        except Exception as e:
            QMessageBox.warning(self, "Rebuild Impact Scenario", f"Failed to save scenario: {e}")
            return

        msg = f"Rebuilt scenario '{scenario_name}' from Baseline using current Controls.\n\nNext: Tools → Compute Both."
        if warnings:
            msg += "\n\nWarnings:\n- " + "\n- ".join(warnings[:10])
            if len(warnings) > 10:
                msg += f"\n- … and {len(warnings) - 10} more"
        QMessageBox.information(self, "Rebuild Impact Scenario", msg)
