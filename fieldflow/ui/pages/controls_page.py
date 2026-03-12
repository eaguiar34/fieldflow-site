from __future__ import annotations

from datetime import date
from typing import Dict

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QMessageBox

from fieldflow.ui.shell.app_context import AppContext
from fieldflow.app.controls_store import ControlsStore
from fieldflow.app.cost_forecast import build_weekly_cost_forecast
from fieldflow.app.rate_library import RateLibraryStore


class ControlsPage(QWidget):
    """
    Controls: Work Packages + Cost Forecast (schedule-driven).

    Adds:
      - Rate Library editor (crews/equipment)
      - Unit converter helper
      - Forecast distribution styles per WP
    """
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.store = ControlsStore()
        self.rate_lib = RateLibraryStore()

        layout = QVBoxLayout(self)

        title = QLabel("Controls: Work Packages & Cost Forecast")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        row = QHBoxLayout()
        self.btn_reload = QPushButton("Reload")
        self.btn_save = QPushButton("Save")
        self.btn_lib = QPushButton("Libraries…")
        self.btn_conv = QPushButton("Convert…")
        row.addWidget(self.btn_reload)
        row.addWidget(self.btn_save)
        row.addWidget(self.btn_lib)
        row.addWidget(self.btn_conv)
        row.addStretch(1)
        layout.addLayout(row)

        self.wp = None
        self.cf = None

        try:
            from fieldflow.ui.work_packages_dock import WorkPackagesDock
            self.wp = WorkPackagesDock()
            layout.addWidget(self.wp, 2)
        except Exception as e:
            layout.addWidget(QLabel(f"WorkPackagesDock not available: {e}"))

        try:
            from fieldflow.ui.cost_forecast_dock import CostForecastDock
            self.cf = CostForecastDock()
            layout.addWidget(self.cf, 2)
        except Exception as e:
            layout.addWidget(QLabel(f"CostForecastDock not available: {e}"))

        self.btn_reload.clicked.connect(self.reload_from_context)
        self.btn_save.clicked.connect(self._save_controls)
        self.btn_lib.clicked.connect(self._open_library)
        self.btn_conv.clicked.connect(self._open_converter)

        if self.wp is not None and hasattr(self.wp, "changed"):
            try:
                self.wp.changed.connect(self._save_controls)
            except Exception:
                pass

        ctx.signals.schedule_computed.connect(self.refresh_from_schedule)
        ctx.signals.project_loaded.connect(self.reload_from_context)
        ctx.signals.active_scenario_changed.connect(lambda _: self.refresh_from_schedule())

        self.reload_from_context()

        # Read-only gating (workspace lock / roles).
        try:
            if getattr(self.ctx, "is_read_only", False):
                self.btn_save.setEnabled(False)
                self.btn_lib.setEnabled(False)
                if self.wp is not None:
                    fn = getattr(self.wp, "set_read_only", None)
                    if callable(fn):
                        fn(True)
        except Exception:
            pass

    def _open_library(self) -> None:
        try:
            from fieldflow.ui.controls.rate_library_dialog import RateLibraryDialog
            RateLibraryDialog(self).exec()
            self.refresh_from_schedule()
        except Exception as e:
            QMessageBox.warning(self, "Rate Library", str(e))

    def _open_converter(self) -> None:
        try:
            from fieldflow.ui.controls.unit_converter_dialog import UnitConverterDialog
            UnitConverterDialog(self).exec()
        except Exception as e:
            QMessageBox.warning(self, "Unit Converter", str(e))

    def reload_from_context(self) -> None:
        try:
            wps, _, _ = self.store.load(self.ctx.project_key)
        except Exception as e:
            QMessageBox.warning(self, "Controls", f"Failed to load controls: {e}")
            wps = []

        if self.wp is not None and hasattr(self.wp, "set_items"):
            try:
                self.wp.set_items(wps)
            except Exception:
                pass

        self.refresh_from_schedule()

    def _save_controls(self) -> None:
        if getattr(self.ctx, "is_read_only", False):
            return
        try:
            _, rfis, subs = self.store.load(self.ctx.project_key)
        except Exception:
            rfis, subs = [], []

        new_wps = []
        if self.wp is not None and hasattr(self.wp, "get_items"):
            try:
                new_wps = self.wp.get_items()
            except Exception:
                new_wps = []

        try:
            self.store.save(self.ctx.project_key, new_wps, rfis, subs)
        except Exception as e:
            QMessageBox.warning(self, "Controls", f"Failed to save controls: {e}")
            return

        self.refresh_from_schedule()

    def refresh_from_schedule(self) -> None:
        if self.cf is None:
            return

        try:
            wps, _, _ = self.store.load(self.ctx.project_key)
        except Exception:
            wps = []

        # Apply rate-library refs (crew/equipment) into WP numbers before forecasting
        crew_map = self.rate_lib.crew_map()
        eq_map = self.rate_lib.equip_map()
        for wp in wps:
            if (wp.pricing_mode or "unit").lower() != "crew":
                continue
            if (wp.crew_cost_per_day is None) and getattr(wp, "crew_profile_id", "") and wp.crew_profile_id in crew_map:
                wp.crew_cost_per_day = float(crew_map[wp.crew_profile_id].cost_per_day)
            if (wp.equipment_cost_per_day is None) and getattr(wp, "equip_profile_id", "") and wp.equip_profile_id in eq_map:
                wp.equipment_cost_per_day = float(eq_map[wp.equip_profile_id].cost_per_day)

        res = self.ctx.results.active
        metrics_by_id = getattr(res, "metrics_by_id", None) if res is not None else None
        if not isinstance(metrics_by_id, dict) or not metrics_by_id:
            try:
                self.cf.set_buckets([], ["Compute CPM to generate a schedule-driven cost forecast."])
            except Exception:
                pass
            return

        es_date: Dict[str, date] = {}
        ef_date: Dict[str, date] = {}
        for aid, m in metrics_by_id.items():
            es_idx = getattr(m, "es", None)
            ef_idx = getattr(m, "ef", None)
            try:
                if es_idx is not None:
                    es_date[str(aid)] = self.ctx.calendar.add_working_days(self.ctx.project_start, int(es_idx))
                if ef_idx is not None:
                    ef_date[str(aid)] = self.ctx.calendar.add_working_days(self.ctx.project_start, int(ef_idx))
            except Exception:
                continue

        buckets, warnings = build_weekly_cost_forecast(
            work_packages=wps,
            activity_es_by_id=es_date,
            activity_ef_by_id=ef_date,
            calendar=self.ctx.calendar,
        )
        try:
            self.cf.set_buckets(buckets, warnings)
        except Exception:
            pass