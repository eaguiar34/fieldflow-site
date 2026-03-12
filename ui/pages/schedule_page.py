from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QSplitter,
    QGroupBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
)

from fieldflow.ui.shell.app_context import AppContext
from fieldflow.app.controls_impacts import (
    controls_provenance_entries_for_activity,
)
from fieldflow.app.controls_store import ControlsStore
from fieldflow.app.services import ActivityRow, apply_cpm_to_rows, compute_cpm_for_project
from fieldflow.app.project_state import ProjectState
from fieldflow.domain.scheduling.cpm import CPMError
from fieldflow.domain.scheduling.types import Activity


def _fmt_date_from_idx(ctx: AppContext, idx: Optional[int]) -> str:
    if idx is None:
        return "—"
    try:
        return str(ctx.calendar.add_working_days(ctx.project_start, idx))
    except Exception:
        return str(idx)


def _parse_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


class SchedulePage(QWidget):
    """Schedule page with Inspector + Critical list + Controls provenance."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._id_to_row: dict[str, int] = {}
        self._controls_store = ControlsStore()

        root = QVBoxLayout(self)

        self.header = QLabel("")
        self.header.setStyleSheet("font-size: 14px; font-weight: 600;")
        root.addWidget(self.header)

        btn_row = QHBoxLayout()
        self.btn_compute = QPushButton("Compute CPM")
        self.btn_both = QPushButton("Compute Both (Baseline + Active)")
        btn_row.addWidget(self.btn_compute)
        btn_row.addWidget(self.btn_both)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Dur", "SNET", "FNET", "ES", "EF", "LS", "LF", "TF", "Critical"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.itemChanged.connect(self._on_item_changed)
        splitter.addWidget(self.table)

        # Inspector pane
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)

        insp = QGroupBox("Inspector")
        form = QFormLayout(insp)

        self.lbl_id = QLabel("—")
        self.lbl_name = QLabel("—")
        self.lbl_dur = QLabel("—")
        self.lbl_snet = QLabel("—")
        self.lbl_fnet = QLabel("—")
        self.lbl_es = QLabel("—")
        self.lbl_ef = QLabel("—")
        self.lbl_ls = QLabel("—")
        self.lbl_lf = QLabel("—")
        self.lbl_tf = QLabel("—")
        self.lbl_crit = QLabel("—")
        self.lbl_name.setWordWrap(True)

        form.addRow("ID:", self.lbl_id)
        form.addRow("Name:", self.lbl_name)
        form.addRow("Duration:", self.lbl_dur)
        form.addRow("SNET:", self.lbl_snet)
        form.addRow("FNET:", self.lbl_fnet)
        form.addRow("ES:", self.lbl_es)
        form.addRow("EF:", self.lbl_ef)
        form.addRow("LS:", self.lbl_ls)
        form.addRow("LF:", self.lbl_lf)
        form.addRow("Total Float:", self.lbl_tf)
        form.addRow("Critical:", self.lbl_crit)

        right_layout.addWidget(insp)

        why_box = QGroupBox("Why (Controls)")
        why_layout = QVBoxLayout(why_box)
        self.lbl_why_hint = QLabel("Click an item to jump to the underlying RFI/Submittal.")
        self.lbl_why_hint.setWordWrap(True)
        self.lbl_why_hint.setStyleSheet("color: #666;")
        why_layout.addWidget(self.lbl_why_hint)

        self.lst_why = QListWidget()
        self.lst_why.itemActivated.connect(self._on_why_activated)
        why_layout.addWidget(self.lst_why)
        right_layout.addWidget(why_box)

        crit_box = QGroupBox("Critical list")
        crit_box_layout = QVBoxLayout(crit_box)
        self.lst_critical = QListWidget()
        self.lst_critical.itemSelectionChanged.connect(self._on_critical_selected)
        crit_box_layout.addWidget(self.lst_critical)
        right_layout.addWidget(crit_box, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([1450, 450])

        root.addWidget(splitter, 1)
        self._splitter = splitter

        self.btn_compute.clicked.connect(self.compute_active)
        self.btn_both.clicked.connect(self.compute_both)

        ctx.signals.active_scenario_changed.connect(lambda _: self.reload_from_context())
        ctx.signals.project_loaded.connect(self.reload_from_context)

        if hasattr(ctx.signals, "ui_zoom_changed"):
            ctx.signals.ui_zoom_changed.connect(self.apply_zoom)
        if hasattr(ctx.signals, "ui_theme_changed"):
            ctx.signals.ui_theme_changed.connect(self.apply_theme)

        if self.table.selectionModel() is not None:
            self.table.selectionModel().selectionChanged.connect(lambda *_: self._refresh_inspector_from_selection())

        self.reload_from_context()
        if hasattr(ctx, "get_zoom_percent"):
            self.apply_zoom(ctx.get_zoom_percent())
        if hasattr(ctx, "get_theme"):
            self.apply_theme(ctx.get_theme())

    # -------------------- UI prefs --------------------
    def apply_zoom(self, percent: int) -> None:
        try:
            p = max(70, min(160, int(percent)))
            f = self.table.font()
            f.setPointSize(max(8, int(10 * (p / 100.0))))
            self.table.setFont(f)
            self.table.resizeColumnsToContents()
        except Exception:
            pass

    def apply_theme(self, theme: str) -> None:
        try:
            if theme == "dark":
                self.table.setStyleSheet(
                    "QTableWidget { background: #1e1e1e; color: #eaeaea; gridline-color: #444; }"
                )
            else:
                self.table.setStyleSheet("")
        except Exception:
            pass

    # -------------------- data load --------------------
    def reload_from_context(self) -> None:
        st = self.ctx.active()
        self.header.setText(
            f"{self.ctx.controller.project.name} | Start: {self.ctx.project_start} | Holidays: {len(self.ctx.calendar.holidays)} | "
            f"Active: {st.name} | {len(st.activities)} activities | {len(st.relationships)} links"
        )
        rows = [ActivityRow(a.id, a.name, a.duration_days, snet=a.snet, fnet=a.fnet) for a in st.activities]
        self._load_rows(rows)
        self._refresh_inspector_from_selection()

    def _load_rows(self, rows: list[ActivityRow]) -> None:
        self._id_to_row.clear()
        self.table.blockSignals(True)
        self.lst_critical.blockSignals(True)
        try:
            self.table.setRowCount(len(rows))
            self.lst_critical.clear()

            critical_bg = QBrush(QColor(255, 240, 240))
            critical_font = QFont()
            critical_font.setBold(True)

            critical_items: list[tuple[int, str, str]] = []

            for r, a in enumerate(rows):
                self._id_to_row[a.id] = r
                is_critical = (a.total_float_days == 0) if a.total_float_days is not None else False
                snet_text = "" if a.snet is None else str(a.snet)
                fnet_text = "" if a.fnet is None else str(a.fnet)

                items = [
                    QTableWidgetItem(a.id),
                    QTableWidgetItem(a.name),
                    QTableWidgetItem(str(a.duration_days)),
                    QTableWidgetItem(snet_text),
                    QTableWidgetItem(fnet_text),
                    QTableWidgetItem(_fmt_date_from_idx(self.ctx, a.es)),
                    QTableWidgetItem(_fmt_date_from_idx(self.ctx, a.ef)),
                    QTableWidgetItem(_fmt_date_from_idx(self.ctx, a.ls)),
                    QTableWidgetItem(_fmt_date_from_idx(self.ctx, a.lf)),
                    QTableWidgetItem("—" if a.total_float_days is None else str(a.total_float_days)),
                    QTableWidgetItem("YES" if is_critical else ""),
                ]

                for c, it in enumerate(items):
                    if c in (2, 3, 4):
                        it.setFlags(it.flags() | Qt.ItemIsEditable)
                    else:
                        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(r, c, it)
                    if is_critical:
                        it.setBackground(critical_bg)
                        it.setFont(critical_font)

                if is_critical:
                    es_idx = a.es if a.es is not None else 10**9
                    label = f"{a.id} — {a.name} (ES { _fmt_date_from_idx(self.ctx, a.es) })"
                    critical_items.append((es_idx, a.id, label))

            for _, aid, label in sorted(critical_items, key=lambda t: (t[0], t[1])):
                it = QListWidgetItem(label)
                it.setData(Qt.UserRole, aid)
                self.lst_critical.addItem(it)

            self.table.resizeColumnsToContents()
            if self.table.rowCount() and not self.table.selectedItems():
                self.table.selectRow(0)
        finally:
            self.table.blockSignals(False)
            self.lst_critical.blockSignals(False)

    # -------------------- editing --------------------
    def _sync_activities_from_table(self) -> None:
        acts: list[Activity] = []
        for r in range(self.table.rowCount()):
            aid = self.table.item(r, 0).text().strip()
            name = self.table.item(r, 1).text().strip()
            dur = int(float(self.table.item(r, 2).text().strip()))
            snet = _parse_date(self.table.item(r, 3).text())
            fnet = _parse_date(self.table.item(r, 4).text())
            acts.append(Activity(aid, name, dur, snet=snet, fnet=fnet))
        self.ctx.active().activities = acts
        self.ctx.autosave()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() not in (2, 3, 4):
            return

        if item.column() == 2:
            try:
                int(float(item.text().strip()))
            except Exception:
                QMessageBox.warning(self, "Invalid duration", "Duration must be a number.")
                return

        if item.column() in (3, 4):
            if item.text().strip() and _parse_date(item.text()) is None:
                QMessageBox.warning(self, "Invalid date", "Use YYYY-MM-DD or leave blank.")
                return

        self._sync_activities_from_table()

    # -------------------- inspector + provenance --------------------
    def _refresh_inspector_from_selection(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        r = items[0].row()

        def cell(c: int) -> str:
            it = self.table.item(r, c)
            return "—" if it is None else (it.text() or "—")

        aid = cell(0).strip()
        self.lbl_id.setText(aid or "—")
        self.lbl_name.setText(cell(1))
        self.lbl_dur.setText(cell(2))
        self.lbl_snet.setText(cell(3) or "—")
        self.lbl_fnet.setText(cell(4) or "—")
        self.lbl_es.setText(cell(5))
        self.lbl_ef.setText(cell(6))
        self.lbl_ls.setText(cell(7))
        self.lbl_lf.setText(cell(8))
        self.lbl_tf.setText(cell(9))

        crit = "YES" if cell(10).strip().upper() == "YES" else "NO"
        self.lbl_crit.setText(crit)
        if crit == "YES":
            self.lbl_crit.setStyleSheet("font-weight: 800; color: #b00020;")
        else:
            self.lbl_crit.setStyleSheet("font-weight: 700;")

        self._refresh_controls_provenance(aid)

    def _refresh_controls_provenance(self, activity_id: str) -> None:
        try:
            _wps, rfis, subs = self._controls_store.load(self.ctx.project_key)
        except Exception:
            rfis, subs = [], []

        self.lst_why.clear()
        aid = (activity_id or "").strip()
        if not aid:
            self.lst_why.addItem(QListWidgetItem("Select an activity row to see drivers."))
            return

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

    # -------------------- critical list --------------------
    def _on_critical_selected(self) -> None:
        items = self.lst_critical.selectedItems()
        if not items:
            return
        aid = items[0].data(Qt.UserRole)
        if aid is None:
            return
        r = self._id_to_row.get(str(aid))
        if r is None:
            return
        self.table.selectRow(r)
        self.table.scrollToItem(self.table.item(r, 0), QTableWidget.ScrollHint.PositionAtCenter)

    # -------------------- CPM compute --------------------
    def compute_active(self) -> None:
        try:
            self._sync_activities_from_table()
            st = self.ctx.active()

            ps = ProjectState.empty()
            ps.project_start = self.ctx.project_start
            ps.calendar = self.ctx.calendar
            ps.activities = st.activities
            ps.relationships = st.relationships

            cpm = compute_cpm_for_project(ps)
            self.ctx.results.active = cpm
            self.ctx.results.compared_active_name = st.name

            rows = [ActivityRow(a.id, a.name, a.duration_days, snet=a.snet, fnet=a.fnet) for a in st.activities]
            rows = apply_cpm_to_rows(rows, cpm)
            self._load_rows(rows)
            self._refresh_inspector_from_selection()

            self.ctx.signals.schedule_computed.emit()

        except CPMError as e:
            QMessageBox.critical(self, "CPM failed", f"{e}")

    def compute_both(self) -> None:
        try:
            self._sync_activities_from_table()

            st = self.ctx.active()
            ps = ProjectState.empty()
            ps.project_start = self.ctx.project_start
            ps.calendar = self.ctx.calendar
            ps.activities = st.activities
            ps.relationships = st.relationships
            scen_cpm = compute_cpm_for_project(ps)
            self.ctx.results.active = scen_cpm
            self.ctx.results.compared_active_name = st.name

            base = self.ctx.project.baseline
            psb = ProjectState.empty()
            psb.project_start = self.ctx.project_start
            psb.calendar = self.ctx.calendar
            psb.activities = list(base.activities)
            psb.relationships = list(base.relationships)
            base_cpm = compute_cpm_for_project(psb)
            self.ctx.results.baseline = base_cpm

            rows = [ActivityRow(a.id, a.name, a.duration_days, snet=a.snet, fnet=a.fnet) for a in st.activities]
            rows = apply_cpm_to_rows(rows, scen_cpm)
            self._load_rows(rows)
            self._refresh_inspector_from_selection()

            self.ctx.signals.schedule_compared.emit()
            self.ctx.signals.schedule_computed.emit()

        except CPMError as e:
            QMessageBox.critical(self, "CPM failed", f"{e}")
