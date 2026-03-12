from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, List

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QWidget

from fieldflow.ui.onboarding.spotlight import Spotlight


@dataclass
class TourStep:
    title: str
    message: str
    page_id: Optional[str] = None
    highlight: Optional[Callable[[], Optional[QWidget]]] = None


class GuidedTour:
    """
    Minimal guided tour controller.

    Requirements:
      - shell.set_page(page_id: str)
      - shell.pages dict for page existence check (optional but recommended)
    """

    def __init__(self, shell) -> None:
        self.shell = shell
        self.idx = 0

        self.spotlight = Spotlight(shell)

        self.steps: List[TourStep] = [
            TourStep(
                title="Schedule",
                message="This is your schedule table. Import data, then Tools → Compute Both.",
                page_id="schedule",
                highlight=lambda: self._find("ff_schedule_table") or self._page("schedule"),
            ),
            TourStep(
                title="Imports",
                message="Import activities and logic here (CSV or MS Project XML).",
                page_id="imports",
                highlight=lambda: self._find("ff_imports_primary") or self._page("imports"),
            ),
            TourStep(
                title="RFIs",
                message="Track RFIs and link them to activities. Open RFIs can drive delays in an Impact Scenario.",
                page_id="rfis",
                highlight=lambda: self._find("ff_rfis_table") or self._page("rfis"),
            ),
            TourStep(
                title="Submittals",
                message="Track submittals + lead times. Unapproved submittals can push SNET dates.",
                page_id="submittals",
                highlight=lambda: self._find("ff_submittals_table") or self._page("submittals"),
            ),
            TourStep(
                title="Controls / Curves",
                message="Controls includes work packages + cost forecast (a simple curve view). It updates when schedule is computed.",
                page_id="controls",
                highlight=lambda: self._find("ff_cost_forecast") or self._page("controls"),
            ),
            TourStep(
                title="Scenarios",
                message="Build an Impact Scenario and compare deltas vs Baseline.",
                page_id="scenarios",
                highlight=lambda: self._page("scenarios"),
            ),
            TourStep(
                title="Done",
                message="Tour complete. Reopen anytime via Help → Welcome / Walkthrough…",
                page_id=None,
                highlight=None,
            ),
        ]

        self.dlg = _TourDialog(parent=self.shell)
        self.dlg.btn_next.clicked.connect(self.next)
        self.dlg.btn_back.clicked.connect(self.back)
        self.dlg.btn_close.clicked.connect(self.close)

    def start(self) -> None:
        self.idx = 0
        self._apply_step()
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def close(self) -> None:
        self.spotlight.hide()
        self.dlg.close()

    def next(self) -> None:
        if self.idx < len(self.steps) - 1:
            self.idx += 1
            self._apply_step()

    def back(self) -> None:
        if self.idx > 0:
            self.idx -= 1
            self._apply_step()

    def _apply_step(self) -> None:
        self.spotlight.hide()
        step = self.steps[self.idx]

        # Skip steps whose page isn't present in this build
        if step.page_id:
            pages = getattr(self.shell, "pages", {})
            if isinstance(pages, dict) and step.page_id not in pages:
                if self.idx < len(self.steps) - 1:
                    self.idx += 1
                    self._apply_step()
                return

        # Switch page
        if step.page_id and hasattr(self.shell, "set_page"):
            try:
                self.shell.set_page(step.page_id)
            except Exception:
                pass

        # Update dialog
        self.dlg.set_step(self.idx + 1, len(self.steps), step.title, step.message)
        self.dlg.btn_back.setEnabled(self.idx > 0)
        self.dlg.btn_next.setEnabled(self.idx < len(self.steps) - 1)
        self.dlg.btn_next.setText("Finish" if self.idx == len(self.steps) - 1 else "Next")

        # Spotlight after layout settles
        if step.highlight:
            QTimer.singleShot(180, lambda: self._do_highlight(step.highlight))

    def _do_highlight(self, getter: Callable[[], Optional[QWidget]]) -> None:
        try:
            w = getter()
        except Exception:
            w = None
        if w is None:
            return
        self.spotlight.flash(w)

    def _find(self, obj_name: str) -> Optional[QWidget]:
        try:
            return self.shell.findChild(QWidget, obj_name)
        except Exception:
            return None

    def _page(self, page_id: str) -> Optional[QWidget]:
        pages = getattr(self.shell, "pages", {})
        if isinstance(pages, dict):
            return pages.get(page_id)
        return None


class _TourDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("FieldFlow Guided Tour")
        self.setModal(False)
        self.resize(460, 220)

        layout = QVBoxLayout(self)

        self.lbl_step = QLabel("")
        self.lbl_step.setStyleSheet("color: #666;")
        layout.addWidget(self.lbl_step)

        self.lbl_title = QLabel("")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(self.lbl_title)

        self.lbl_msg = QLabel("")
        self.lbl_msg.setWordWrap(True)
        layout.addWidget(self.lbl_msg, 1)

        row = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_next = QPushButton("Next")
        self.btn_close = QPushButton("Close")
        row.addWidget(self.btn_back)
        row.addWidget(self.btn_next)
        row.addStretch(1)
        row.addWidget(self.btn_close)
        layout.addLayout(row)

    def set_step(self, i: int, n: int, title: str, msg: str) -> None:
        self.lbl_step.setText(f"Step {i} of {n}")
        self.lbl_title.setText(title)
        self.lbl_msg.setText(msg)