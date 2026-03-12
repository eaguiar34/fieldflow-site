from __future__ import annotations

from datetime import date
from typing import Dict, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMessageBox

from fieldflow.ui.shell.app_context import AppContext
from fieldflow.app.controls_store import ControlsStore
from fieldflow.app.submittal_checker import check_submittals


class SubmittalsPage(QWidget):
    """Submittals page backed by ControlsStore + checker.

    Supports deep-link focusing via focus_item(submittal_id).
    """

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.store = ControlsStore()

        layout = QVBoxLayout(self)
        title = QLabel("Submittals")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        self.dock = None
        try:
            from fieldflow.ui.submittals_dock import SubmittalsDock

            self.dock = SubmittalsDock()
            layout.addWidget(self.dock, 1)
        except Exception as e:
            layout.addWidget(QLabel(f"SubmittalsDock not available: {e}"))

        if self.dock is not None and hasattr(self.dock, "changed"):
            try:
                self.dock.changed.connect(self._save_and_check)  # type: ignore[attr-defined]
            except Exception:
                pass

        ctx.signals.project_loaded.connect(self.reload_from_context)
        ctx.signals.schedule_computed.connect(self._check_only)
        ctx.signals.active_scenario_changed.connect(lambda _: self._check_only())

        self.reload_from_context()

        # Flash state
        self._flash_timer: Optional[QTimer] = None
        self._flash_prev_brushes: dict[tuple[int, int], QBrush] = {}

    def reload_from_context(self) -> None:
        try:
            _, _, subs = self.store.load(self.ctx.project_key)
        except Exception as e:
            QMessageBox.warning(self, "Submittals", f"Failed to load submittals: {e}")
            subs = []

        if self.dock is not None and hasattr(self.dock, "set_items"):
            try:
                self.dock.set_items(subs)  # type: ignore[attr-defined]
            except Exception:
                pass

        self._check_only()

    def _save_and_check(self) -> None:
        try:
            wps, rfis, _ = self.store.load(self.ctx.project_key)
        except Exception:
            wps, rfis = [], []

        new_subs = []
        if self.dock is not None and hasattr(self.dock, "get_items"):
            try:
                new_subs = self.dock.get_items()  # type: ignore[attr-defined]
            except Exception:
                new_subs = []

        try:
            self.store.save(self.ctx.project_key, wps, rfis, new_subs)
        except Exception as e:
            QMessageBox.warning(self, "Submittals", f"Failed to save submittals: {e}")
            return

        self._check_only()

    def _check_only(self) -> None:
        if self.dock is None or not hasattr(self.dock, "set_findings"):
            return

        try:
            _, _, subs = self.store.load(self.ctx.project_key)
        except Exception:
            subs = []

        res = self.ctx.results.active
        metrics_by_id = getattr(res, "metrics_by_id", None) if res is not None else None

        es_date: Dict[str, date] = {}
        if isinstance(metrics_by_id, dict):
            for aid, m in metrics_by_id.items():
                es_idx = getattr(m, "es", None)
                if es_idx is None:
                    continue
                try:
                    es_date[str(aid)] = self.ctx.calendar.add_working_days(self.ctx.project_start, int(es_idx))
                except Exception:
                    continue

        findings = check_submittals(
            submittals=subs,
            activity_start_by_id=es_date,
            calendar=self.ctx.calendar,
            today=date.today(),
        )

        try:
            self.dock.set_findings(findings)  # type: ignore[attr-defined]
        except Exception:
            pass

    # -------------------- deep-link support --------------------
    def focus_item(self, submittal_id: str) -> None:
        """Select + flash a Submittal row by id."""
        if self.dock is None:
            return
        table = getattr(self.dock, "table", None)
        if table is None:
            return

        sid = (submittal_id or "").strip()
        if not sid:
            return

        target_row = None
        for r in range(table.rowCount()):
            it = table.item(r, 0)
            if it is not None and it.text().strip() == sid:
                target_row = r
                break

        if target_row is None:
            return

        table.setCurrentCell(target_row, 0)
        table.selectRow(target_row)
        try:
            table.scrollToItem(table.item(target_row, 0), table.ScrollHint.PositionAtCenter)
        except Exception:
            pass

        self._flash_row(table, target_row)

    def _flash_row(self, table, row: int) -> None:
        self._clear_flash(table)

        color = QBrush(QColor(255, 245, 157))
        cols = table.columnCount()
        for c in range(cols):
            it = table.item(row, c)
            if it is None:
                continue
            self._flash_prev_brushes[(row, c)] = it.background()
            it.setBackground(color)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: self._clear_flash(table))
        self._flash_timer.start(1500)

    def _clear_flash(self, table) -> None:
        if not self._flash_prev_brushes:
            return
        for (r, c), brush in list(self._flash_prev_brushes.items()):
            it = table.item(r, c)
            if it is not None:
                it.setBackground(brush)
        self._flash_prev_brushes.clear()
        if self._flash_timer is not None:
            try:
                self._flash_timer.stop()
            except Exception:
                pass
            self._flash_timer = None
