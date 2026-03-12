from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMessageBox

from fieldflow.ui.shell.app_context import AppContext
from fieldflow.app.controls_store import ControlsStore


class RFIsPage(QWidget):
    """RFIs page backed by ControlsStore.

    Supports deep-link focusing via focus_item(rfi_id).
    """

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.store = ControlsStore()

        layout = QVBoxLayout(self)
        title = QLabel("RFIs")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        self.dock = None
        try:
            from fieldflow.ui.rfi_dock import RFIDock

            self.dock = RFIDock()
            layout.addWidget(self.dock, 1)
        except Exception as e:
            layout.addWidget(QLabel(f"RFIDock not available: {e}"))

        if self.dock is not None and hasattr(self.dock, "changed"):
            try:
                self.dock.changed.connect(self._save)  # type: ignore[attr-defined]
            except Exception:
                pass

        ctx.signals.project_loaded.connect(self.reload_from_context)
        self.reload_from_context()

        # Highlight cleanup
        self._flash_timer: Optional[QTimer] = None
        self._flash_rows: list[int] = []
        self._flash_prev_brushes: dict[tuple[int, int], QBrush] = {}

    def reload_from_context(self) -> None:
        try:
            _, rfis, _ = self.store.load(self.ctx.project_key)
        except Exception as e:
            QMessageBox.warning(self, "RFIs", f"Failed to load RFIs: {e}")
            rfis = []

        if self.dock is not None and hasattr(self.dock, "set_items"):
            try:
                self.dock.set_items(rfis)  # type: ignore[attr-defined]
            except Exception:
                pass

    def _save(self) -> None:
        # Preserve other controls (WPs/Submittals)
        try:
            wps, _, subs = self.store.load(self.ctx.project_key)
        except Exception:
            wps, subs = [], []

        new_rfis = []
        if self.dock is not None and hasattr(self.dock, "get_items"):
            try:
                new_rfis = self.dock.get_items()  # type: ignore[attr-defined]
            except Exception:
                new_rfis = []

        try:
            self.store.save(self.ctx.project_key, wps, new_rfis, subs)
        except Exception as e:
            QMessageBox.warning(self, "RFIs", f"Failed to save RFIs: {e}")

    # -------------------- deep-link support --------------------
    def focus_item(self, rfi_id: str) -> None:
        """Select + flash an RFI row by id."""
        if self.dock is None:
            return
        table = getattr(self.dock, "table", None)
        if table is None:
            return

        rid = (rfi_id or "").strip()
        if not rid:
            return

        # Best effort: assume ID is in column 0
        target_row = None
        for r in range(table.rowCount()):
            it = table.item(r, 0)
            if it is not None and it.text().strip() == rid:
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
        # Clear any existing flash first
        self._clear_flash(table)

        color = QBrush(QColor(255, 245, 157))  # soft yellow
        self._flash_rows = [row]

        # Save previous brushes per cell and apply
        cols = table.columnCount()
        for c in range(cols):
            it = table.item(row, c)
            if it is None:
                continue
            self._flash_prev_brushes[(row, c)] = it.background()
            it.setBackground(color)

        # Remove flash after 1.5s
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
        self._flash_rows = []
        if self._flash_timer is not None:
            try:
                self._flash_timer.stop()
            except Exception:
                pass
            self._flash_timer = None
