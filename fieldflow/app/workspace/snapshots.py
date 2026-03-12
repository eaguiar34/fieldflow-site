from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class SnapshotInfo:
    folder: Path
    tag: str


class SnapshotManager:
    def __init__(self, workspace_root: Path) -> None:
        self.root = Path(workspace_root)
        self.snapshots_dir = self.root / "snapshots"

    def publish(self, tag: str = "") -> SnapshotInfo:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Keep snapshot folder names filesystem-friendly.
        safe_tag = "".join([c for c in (tag or "") if c.isalnum() or c in ("-", "_", " ")])
        safe_tag = safe_tag.strip().replace(" ", "_")
        name = ts if not safe_tag else f"{ts}_{safe_tag}"
        dest = self.snapshots_dir / name
        dest.mkdir(parents=True, exist_ok=True)

        # Copy key artifacts
        for rel in ["project.ffproj.json", "events/events.jsonl"]:
            src = self.root / rel
            if src.exists():
                (dest / Path(rel).parent).mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest / rel)

        return SnapshotInfo(folder=dest, tag=tag)

    def latest_snapshot_folder(self) -> Optional[Path]:
        if not self.snapshots_dir.exists():
            return None
        snaps = [p for p in self.snapshots_dir.iterdir() if p.is_dir()]
        if not snaps:
            return None
        return sorted(snaps, key=lambda p: p.name)[-1]