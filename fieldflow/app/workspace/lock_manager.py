from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


@dataclass
class LockInfo:
    owner: str
    machine: str
    expires_utc: str


class LockManager:
    """
    Lease-based lock using a JSON file in workspace/locks/.

    - Acquire: write lock if missing or expired.
    - Renew: update expiry.
    - Release: delete lock (best-effort).

    This is intentionally simple and friendly to network shares.
    """

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = Path(lock_path)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _who(self) -> tuple[str, str]:
        user = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
        machine = socket.gethostname() or "unknown_machine"
        return user, machine

    def read(self) -> Optional[LockInfo]:
        if not self.lock_path.exists():
            return None
        try:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            return LockInfo(
                owner=str(data.get("owner", "")),
                machine=str(data.get("machine", "")),
                expires_utc=str(data.get("expires_utc", "")),
            )
        except Exception:
            return None

    def is_expired(self, info: LockInfo) -> bool:
        try:
            exp = datetime.fromisoformat(info.expires_utc.replace("Z", "+00:00"))
            return self._now() >= exp
        except Exception:
            return True

    def acquire(self, *, lease_seconds: int = 60) -> bool:
        info = self.read()
        if info is not None and not self.is_expired(info):
            return False

        user, machine = self._who()
        exp = self._now() + timedelta(seconds=int(lease_seconds))
        payload = {
            "owner": user,
            "machine": machine,
            "expires_utc": exp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        try:
            self.lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    def renew(self, *, lease_seconds: int = 60) -> bool:
        info = self.read()
        if info is None:
            return False
        user, machine = self._who()
        # Only renew if we are the owner (best-effort)
        if info.owner and info.owner != user:
            return False

        exp = self._now() + timedelta(seconds=int(lease_seconds))
        payload = {
            "owner": user,
            "machine": machine,
            "expires_utc": exp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        try:
            self.lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    def release(self) -> None:
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except Exception:
            pass