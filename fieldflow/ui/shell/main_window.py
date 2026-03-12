from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette, QColor, QAction
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QStackedWidget,
    QSplitter,
    QDockWidget,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QTableWidget,
)

from fieldflow.ui.shell.app_context import AppContext
from fieldflow.ui.shell.nav import SidebarNav
from fieldflow.ui.shell.actions import Actions

from fieldflow.ui.pages.schedule_page import SchedulePage
from fieldflow.ui.pages.logic_page import LogicPage
from fieldflow.ui.pages.scenarios_page import ScenariosPage
from fieldflow.ui.pages.controls_page import ControlsPage

try:
    from fieldflow.ui.pages.calendar_page import CalendarPage
except Exception:
    CalendarPage = None
try:
    from fieldflow.ui.pages.imports_page import ImportsPage
except Exception:
    ImportsPage = None
try:
    from fieldflow.ui.pages.rfi_page import RFIsPage
except Exception:
    RFIsPage = None
try:
    from fieldflow.ui.pages.submittals_page import SubmittalsPage
except Exception:
    SubmittalsPage = None


class ShellMainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("FieldFlow")
        self.resize(1900, 980)

        self.actions = Actions(ctx, self)

        # Diagnostics dock
        self.diag = QTextEdit()
        self.diag.setReadOnly(True)
        self.diag.setPlainText("Diagnostics will appear here.")
        dock = QDockWidget("Diagnostics", self)
        dock.setWidget(self.diag)
        dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self._diag_dock = dock

        self.statusBar().showMessage("Ready")

        # Menus
        self._build_menus()

        # Pages
        self.nav = SidebarNav()
        self.stack = QStackedWidget()

        page_defs = [
            ("schedule", "Schedule", SchedulePage),
            ("logic", "Logic", LogicPage),
        ]
        if CalendarPage is not None:
            page_defs.append(("calendar", "Calendar", CalendarPage))
        if ImportsPage is not None:
            page_defs.append(("imports", "Imports", ImportsPage))
        page_defs.extend([
            ("scenarios", "Scenarios", ScenariosPage),
            ("controls", "Controls (Cost)", ControlsPage),
        ])
        if RFIsPage is not None:
            page_defs.append(("rfis", "RFIs", RFIsPage))
        if SubmittalsPage is not None:
            page_defs.append(("submittals", "Submittals", SubmittalsPage))

        self.page_ids = [pid for pid, _, _ in page_defs]
        self.page_labels = {pid: label for pid, label, _ in page_defs}
        self.nav.set_pages(self.page_ids, self.page_labels)
        self.nav.page_selected.connect(self.set_page)

        self.pages: dict[str, QWidget] = {}
        for pid, _, cls in page_defs:
            try:
                w = cls(ctx)
            except Exception as e:
                w = QTextEdit()
                w.setReadOnly(True)
                w.setPlainText(f"Failed to load page '{pid}':\n{e}")
            self.pages[pid] = w
            self.stack.addWidget(w)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Horizontal)
        splitter.addWidget(self.nav)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 1600])

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.setCentralWidget(central)
        self._splitter = splitter

        # Wire actions
        self.actions.exit_app.triggered.connect(self.close)
        self.actions.reset_layout.triggered.connect(self.reset_layout)

        self.actions.open_project.triggered.connect(self._open_project)
        self.actions.open_workspace.triggered.connect(self._open_workspace_folder)
        self.actions.save_project_as.triggered.connect(self._save_project_as)
        self.actions.publish_snapshot.triggered.connect(self._publish_snapshot)
        self.actions.changes_since.triggered.connect(self._changes_since)
        self.actions.sync_now.triggered.connect(self._sync_now)

        # Tools (use safe wrappers)
        self.actions.compute_cpm.triggered.connect(self.compute_active_safe)
        self.actions.compute_both.triggered.connect(self.compute_both_safe)

        # Edit routing
        self.actions.import_activities.triggered.connect(lambda: self._go_if_exists("imports"))
        self.actions.import_logic.triggered.connect(lambda: self._go_if_exists("imports"))
        self.actions.set_start_date.triggered.connect(lambda: self._go_if_exists("calendar"))
        self.actions.clear_holidays.triggered.connect(self._clear_holidays)

        # Help
        self.actions.welcome_walkthrough.triggered.connect(self.show_welcome_dialog)
        self.actions.reset_onboarding.triggered.connect(self._reset_onboarding)

        # Theme
        self._act_theme_light.triggered.connect(lambda: self.ctx.set_theme("light"))
        self._act_theme_dark.triggered.connect(lambda: self.ctx.set_theme("dark"))
        self.ctx.signals.ui_theme_changed.connect(self.apply_theme)
        self.apply_theme(self.ctx.get_theme())

        # Zoom propagate
        if hasattr(self.ctx.signals, "ui_zoom_changed"):
            self.ctx.signals.ui_zoom_changed.connect(lambda _: self._apply_zoom_to_pages())
        self._apply_zoom_to_pages()

        # Recent projects
        if hasattr(self.ctx.signals, "recent_projects_changed"):
            self.ctx.signals.recent_projects_changed.connect(self._rebuild_recent_menu)
        self._rebuild_recent_menu()

        # Restore state and select last page
        self._restore_ui_state()
        self.nav.set_current(self.current_page_id())

        # Onboarding after layout/paint
        QTimer.singleShot(250, self._maybe_show_welcome)

        # Housekeeping: renew lock + merge shared-folder events.
        self._house_timer = QTimer(self)
        self._house_timer.setInterval(25_000)
        self._house_timer.timeout.connect(self._housekeeping_tick)
        self._house_timer.start()

        self._update_status_from_workspace()
        self._apply_read_only_gates()

    def log(self, msg: str) -> None:
        self.diag.append(msg)
        self.statusBar().showMessage(msg, 4000)

    def _update_status_from_workspace(self) -> None:
        try:
            txt = self.ctx.workspace_status_text()
            if txt:
                self.statusBar().showMessage(txt)
        except Exception:
            pass

    def _housekeeping_tick(self) -> None:
        try:
            self.ctx.renew_lock_if_owned()
        except Exception:
            pass
        try:
            self.ctx.merge_events_now()
        except Exception:
            pass
        self._update_status_from_workspace()

    def _apply_read_only_gates(self) -> None:
        ro = bool(getattr(self.ctx, "is_read_only", False))
        # Disable editing entrypoints.
        for act in [
            self.actions.import_activities,
            self.actions.import_logic,
            self.actions.set_start_date,
            self.actions.clear_holidays,
            self.actions.save_project_as,
            self.actions.publish_snapshot,
        ]:
            try:
                act.setEnabled(not ro)
            except Exception:
                pass

    # ---------------- safe compute wrappers ----------------
    def compute_active_safe(self) -> None:
        sch = self.pages.get("schedule")
        fn = getattr(sch, "compute_active", None) if sch is not None else None
        if callable(fn):
            try:
                fn()
                return
            except Exception as e:
                QMessageBox.warning(self, "Compute CPM", str(e))
                return
        QMessageBox.information(self, "Compute CPM", "Schedule page not available in this build.")

    def compute_both_safe(self) -> None:
        sch = self.pages.get("schedule")
        fn = getattr(sch, "compute_both", None) if sch is not None else None
        if callable(fn):
            try:
                fn()
                return
            except Exception as e:
                QMessageBox.warning(self, "Compute Both", str(e))
                return
        QMessageBox.information(self, "Compute Both", "Schedule page not available in this build.")

    def open_scenarios_and_select_top_driver(self) -> None:
        """Nice demo touch: jump to Scenarios and select the top delay driver row."""
        if "scenarios" not in self.pages:
            return
        self.set_page("scenarios")
        sc = self.pages.get("scenarios")
        tbl = getattr(sc, "drivers", None)
        if isinstance(tbl, QTableWidget) and tbl.rowCount() > 0:
            try:
                tbl.selectRow(0)
                tbl.scrollToItem(tbl.item(0, 0), QTableWidget.ScrollHint.PositionAtCenter)
            except Exception:
                pass

    # ---------------- onboarding ----------------
    def _maybe_show_welcome(self) -> None:
        try:
            if self.ctx.onboarding_done():
                return
        except Exception:
            return
        self.show_welcome_dialog(auto_mark_done=True)

    def show_welcome_dialog(self, *, auto_mark_done: bool = False) -> None:
        dont_show = auto_mark_done
        try:
            from fieldflow.ui.onboarding.welcome_dialog import WelcomeDialog
            dlg = WelcomeDialog(self.ctx, self)
            dlg.exec()
            dont_show = dont_show or bool(getattr(dlg, "dont_show_again", False))
        except Exception as e:
            QMessageBox.warning(self, "Welcome", f"Failed to open Welcome dialog:\n{e}")
        finally:
            if dont_show:
                try:
                    self.ctx.set_onboarding_done(True)
                except Exception:
                    pass

    def _reset_onboarding(self) -> None:
        try:
            self.ctx.set_onboarding_done(False)
            QMessageBox.information(
                self,
                "Onboarding",
                "Onboarding reset.\n\nRestart the app to see first-run Welcome again, or use Help → Welcome / Walkthrough…",
            )
        except Exception as e:
            QMessageBox.warning(self, "Onboarding", str(e))

    # ---------------- menus ----------------
    def _build_menus(self) -> None:
        mb = self.menuBar()

        self._m_file = mb.addMenu("File")
        m_edit = mb.addMenu("Edit")
        m_tools = mb.addMenu("Tools")
        m_view = mb.addMenu("View")
        m_help = mb.addMenu("Help")
        m_tut = mb.addMenu("Tutorials")

        self._m_file.addAction(self.actions.open_project)
        self._m_file.addAction(self.actions.open_workspace)
        self._m_file.addAction(self.actions.save_project_as)
        self._m_file.addSeparator()
        self._m_file.addAction(self.actions.publish_snapshot)
        self._m_file.addSeparator()
        self._m_recent = self._m_file.addMenu("Recent Projects")
        self._m_file.addSeparator()
        self._m_file.addAction(self.actions.exit_app)

        m_edit.addAction(self.actions.import_activities)
        m_edit.addAction(self.actions.import_logic)
        m_edit.addSeparator()
        m_edit.addAction(self.actions.set_start_date)
        m_edit.addAction(self.actions.clear_holidays)

        m_tools.addAction(self.actions.compute_cpm)
        m_tools.addAction(self.actions.compute_both)
        m_tools.addSeparator()
        m_tools.addAction(self.actions.changes_since)
        m_tools.addAction(self.actions.sync_now)

        theme_menu = m_view.addMenu("Theme")
        self._act_theme_light = QAction("Light", self)
        self._act_theme_dark = QAction("Dark", self)
        theme_menu.addAction(self._act_theme_light)
        theme_menu.addAction(self._act_theme_dark)

        m_view.addSeparator()
        m_view.addAction(self.actions.reset_layout)
        m_view.addAction(self._diag_dock.toggleViewAction())

        m_help.addAction(self.actions.welcome_walkthrough)
        m_help.addAction(self.actions.reset_onboarding)
        m_help.addSeparator()
        m_help.addAction(self.actions.about)
        m_tut.addAction(self.actions.tutorials)

    # ---------------- recent projects ----------------
    def _rebuild_recent_menu(self) -> None:
        self._m_recent.clear()
        try:
            recents = self.ctx.recent_projects()
        except Exception:
            recents = []
        if not recents:
            act = QAction("(none)", self)
            act.setEnabled(False)
            self._m_recent.addAction(act)
            return
        for p in recents:
            act = QAction(p, self)
            act.triggered.connect(lambda checked=False, path=p: self._open_recent(path))
            self._m_recent.addAction(act)

    def _open_recent(self, path: str) -> None:
        try:
            p = Path(path)
            if p.exists() and p.is_dir():
                self.ctx.open_workspace_folder(p)
                self.log(f"Opened workspace: {path}")
            else:
                self.ctx.open_project_file(p)
                self.log(f"Opened project: {path}")
            self._reload_pages()
            self._update_status_from_workspace()
            self._apply_read_only_gates()
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    # ---------------- helpers ----------------
    def _reload_pages(self) -> None:
        for w in self.pages.values():
            fn = getattr(w, "reload_from_context", None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass

    def _go_if_exists(self, pid: str) -> None:
        if pid in self.pages:
            self.set_page(pid)

    def set_page(self, pid: str) -> None:
        if pid not in self.pages:
            return
        w = self.pages[pid]
        self.stack.setCurrentWidget(w)
        self.nav.set_current(pid)

    def current_page_id(self) -> str:
        cur = self.stack.currentWidget()
        for pid, w in self.pages.items():
            if w is cur:
                return pid
        return "schedule"

    # ---------------- file ops ----------------
    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open FieldFlow Project",
            str(Path.home()),
            "FieldFlow Project (*.fieldflow);;All Files (*.*)",
        )
        if not path:
            return
        try:
            self.ctx.open_project_file(Path(path))
            self.log(f"Opened project: {path}")
            self._reload_pages()
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    def _open_workspace_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Workspace Folder")
        if not folder:
            return
        try:
            self.ctx.open_workspace_folder(Path(folder))
            self.log(f"Opened workspace folder: {folder}")
            self._reload_pages()
            self._update_status_from_workspace()
            self._apply_read_only_gates()
        except Exception as e:
            QMessageBox.critical(self, "Open Workspace", str(e))

    def _sync_now(self) -> None:
        try:
            self.ctx.merge_events_now()
            self.log("Sync merge complete.")
        except Exception as e:
            QMessageBox.warning(self, "Sync", str(e))

    def _publish_snapshot(self) -> None:
        if not getattr(self.ctx, "snapshots", None):
            QMessageBox.information(self, "Snapshot", "No workspace open. Open a workspace folder first.")
            return
        tag, ok = QInputDialog.getText(self, "Publish Snapshot", "Tag (optional):")
        if not ok:
            return
        try:
            info = self.ctx.snapshots.publish(tag=tag or "")
            self.ctx.append_event(
                entity="snapshot",
                entity_id=self.ctx.project_key,
                op="publish",
                payload={"tag": tag or "", "folder": str(info.folder)},
            )
            self.log(f"Snapshot published: {info.folder}")
        except Exception as e:
            QMessageBox.warning(self, "Snapshot", str(e))

    def _changes_since(self) -> None:
        if not getattr(self.ctx, "event_log", None):
            QMessageBox.information(self, "Changes Since", "No workspace open. Open a workspace folder first.")
            return

        default_iso = (datetime.now(timezone.utc) - timedelta(hours=24)).replace(microsecond=0).isoformat()
        default_iso = default_iso.replace("+00:00", "Z")

        since, ok = QInputDialog.getText(
            self,
            "Changes Since",
            "UTC timestamp (ISO, e.g. 2026-03-11T12:00:00Z):",
            text=default_iso,
        )
        if not ok:
            return
        try:
            from fieldflow.app.workspace.changes_report import changes_since

            events = self.ctx.event_log.read_all(limit=5000)
            rep = changes_since(events, since_utc_iso=str(since).strip())

            dlg = QMessageBox(self)
            dlg.setWindowTitle(rep.title)
            dlg.setIcon(QMessageBox.Information)
            dlg.setText("\n".join(rep.lines[:1200]))
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Changes Since", str(e))

    def _save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save FieldFlow Project As",
            str(Path.home() / "project.fieldflow"),
            "FieldFlow Project (*.fieldflow);;All Files (*.*)",
        )
        if not path:
            return
        name, ok = QInputDialog.getText(self, "Project Name", "Name:", text=self.ctx.controller.project.name)
        if not ok:
            return
        try:
            self.ctx.save_project_as(Path(path), name=name or "Untitled Project")
            self.log(f"Saved project as: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _clear_holidays(self) -> None:
        self.ctx.update_calendar(holidays=set())
        self.log("Cleared holidays.")

    # ---------------- UI state persistence ----------------
    def closeEvent(self, event) -> None:
        try:
            self.ctx.release_lock_if_owned()
        except Exception:
            pass
        self._save_ui_state()
        super().closeEvent(event)

    def _save_ui_state(self) -> None:
        s = self.ctx.qsettings
        pref = self.ctx.settings_prefix()
        try:
            s.setValue(f"{pref}/ui/geometry", self.saveGeometry())
            s.setValue(f"{pref}/ui/state", self.saveState())
            s.setValue(f"{pref}/ui/splitter_sizes", self._splitter.sizes())
            s.setValue(f"{pref}/ui/last_page", self.current_page_id())
        except Exception:
            pass

    def _restore_ui_state(self) -> None:
        s = self.ctx.qsettings
        pref = self.ctx.settings_prefix()

        geo = s.value(f"{pref}/ui/geometry")
        st = s.value(f"{pref}/ui/state")
        sizes = s.value(f"{pref}/ui/splitter_sizes")
        last = s.value(f"{pref}/ui/last_page", "schedule")

        if geo is not None:
            try:
                self.restoreGeometry(geo)
            except Exception:
                pass
        if st is not None:
            try:
                self.restoreState(st)
            except Exception:
                pass
        if isinstance(sizes, list) and len(sizes) == 2:
            try:
                self._splitter.setSizes([int(sizes[0]), int(sizes[1])])
            except Exception:
                pass

        if isinstance(last, str) and last in self.pages:
            self.set_page(last)
        else:
            self.set_page("schedule")

    def reset_layout(self) -> None:
        self._splitter.setSizes([240, 1600])
        self.resize(1900, 980)
        self.log("Layout reset.")