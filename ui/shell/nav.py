from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QSizePolicy


class SidebarNav(QWidget):
    page_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._id_by_row: List[str] = []
        self._labels: Dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- Header (big logo + app name) ---
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(6, 6, 6, 6)
        header_layout.setSpacing(6)

        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        pix = self._load_logo_pixmap()
        if pix is not None and not pix.isNull():
            # 64px is a nice “big but not absurd” sidebar logo size
            self.logo.setPixmap(pix.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo.setText("🛠️")
            self.logo.setStyleSheet("font-size: 28px;")

        self.brand = QLabel("FieldFlow")
        self.brand.setAlignment(Qt.AlignCenter)
        self.brand.setStyleSheet("font-size: 16px; font-weight: 700;")

        header_layout.addWidget(self.logo)
        header_layout.addWidget(self.brand)

        layout.addWidget(header)

        # --- Nav list ---
        self.list = QListWidget()
        self.list.setSpacing(2)
        self.list.itemSelectionChanged.connect(self._emit_selected)
        layout.addWidget(self.list, 1)

    def set_pages(self, page_ids: List[str], labels: Dict[str, str]) -> None:
        self._id_by_row = list(page_ids)
        self._labels = dict(labels)

        self.list.clear()
        for pid in self._id_by_row:
            txt = self._labels.get(pid, pid)
            item = QListWidgetItem(txt)
            self.list.addItem(item)

        if self.list.count() > 0:
            self.list.setCurrentRow(0)

    def set_current(self, page_id: str) -> None:
        if page_id not in self._id_by_row:
            return
        row = self._id_by_row.index(page_id)
        self.list.blockSignals(True)
        try:
            self.list.setCurrentRow(row)
        finally:
            self.list.blockSignals(False)

    def _emit_selected(self) -> None:
        row = self.list.currentRow()
        if row < 0 or row >= len(self._id_by_row):
            return
        self.page_selected.emit(self._id_by_row[row])

    def _load_logo_pixmap(self) -> QPixmap | None:
        # fieldflow/ui/shell/nav.py -> fieldflow/ui/assets/fieldflow_icon.png
        try:
            icon_path = Path(__file__).resolve().parents[1] / "assets" / "fieldflow_icon.png"
            if icon_path.exists():
                return QPixmap(str(icon_path))
        except Exception:
            pass
        return None