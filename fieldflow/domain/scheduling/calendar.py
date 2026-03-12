from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class WorkCalendar:
    """
    Minimal working calendar with exceptions:
    - Mon–Fri are working days
    - holidays/exceptions are non-working days (date objects)
    """
    name: str = "STD"
    holidays: set[date] = field(default_factory=set)

    def is_working_day(self, d: date) -> bool:
        if d in self.holidays:
            return False
        return d.weekday() < 5  # Mon=0 ... Fri=4

    def next_working_day(self, d: date) -> date:
        cur = d
        while not self.is_working_day(cur):
            cur += timedelta(days=1)
        return cur

    def add_working_days(self, start: date, working_days: int) -> date:
        """
        Return the date that is `working_days` working days after `start`.
        working_days=0 returns start.
        Skips weekends + holidays.
        """
        if working_days == 0:
            return start

        step = 1 if working_days > 0 else -1
        remaining = abs(working_days)
        cur = start

        while remaining > 0:
            cur = cur + timedelta(days=step)
            if self.is_working_day(cur):
                remaining -= 1

        return cur

    def working_day_index(self, start: date, target: date, snap_forward: bool = True) -> int:
        """
        Convert a real date into a working-day offset from `start` using this calendar.

        If snap_forward=True, a non-working target snaps to the next working day.
        """
        if snap_forward:
            target = self.next_working_day(target)

        if target == start:
            return 0

        if target > start:
            cur = start
            idx = 0
            while cur < target:
                cur = cur + timedelta(days=1)
                if self.is_working_day(cur):
                    idx += 1
            return idx

        # target < start
        cur = start
        idx = 0
        while cur > target:
            cur = cur - timedelta(days=1)
            if self.is_working_day(cur):
                idx -= 1
        return idx
