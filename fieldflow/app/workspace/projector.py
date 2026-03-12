from __future__ import annotations

"""
Workspace projector: connects rebuilder -> projections.

This stays in app/ workspace layer: it doesn't touch CPM or UI.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fieldflow.app.workspace.rebuilder import WorkspaceRebuilder, ReplayStats
from fieldflow.app.workspace.projections_controls import ControlsWorkPackagesProjection


@dataclass
class ProjectorStats:
    replay: ReplayStats


class WorkspaceProjector:
    def __init__(self, workspace_root: Path) -> None:
        self.root = Path(workspace_root)
        self.rebuilder = WorkspaceRebuilder(self.root)

        # projections live under cache/projections/
        self.controls_wps = ControlsWorkPackagesProjection(self.rebuilder.projections_dir)

        # register handlers
        self.rebuilder.register_handler(self.controls_wps.apply)

    def replay_incremental(self) -> ProjectorStats:
        rep = self.rebuilder.replay_incremental()
        return ProjectorStats(replay=rep)