from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMessageBox

from fieldflow.ui.shell.app_context import AppContext
from fieldflow.ui.relationships_view import RelationshipsView
from fieldflow.app.services import relationships_from_import


class LogicPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx

        layout = QVBoxLayout(self)
        title = QLabel("Logic (Relationships)")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        self.view = RelationshipsView()
        layout.addWidget(self.view, 1)

        self.view.btn_add.clicked.connect(self._add)
        self.view.btn_delete.clicked.connect(self._delete)
        self.view.table.itemChanged.connect(lambda _: self._sync_from_view())

        ctx.signals.active_scenario_changed.connect(lambda _: self.reload())
        ctx.signals.project_loaded.connect(self.reload)

        self.reload()

    def reload(self) -> None:
        st = self.ctx.active()
        self.view.set_rows([(r.pred_id, r.succ_id, r.rel_type.value, r.lag_days) for r in st.relationships])

    def _sync_from_view(self) -> None:
        try:
            self.ctx.active().relationships = relationships_from_import(self.view.get_rows())
            self.ctx.autosave()
        except Exception as e:
            QMessageBox.warning(self, "Relationships", str(e))

    def _add(self) -> None:
        self.view.add_blank_row()
        self._sync_from_view()

    def _delete(self) -> None:
        if self.view.delete_selected_row():
            self._sync_from_view()
