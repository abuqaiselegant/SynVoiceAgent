"""The slot engine. Free slots = a practitioner's working hours, minus their breaks, minus their
already-booked appointments, sliced into the requested treatment's duration.

This is the single most error-prone piece in the product, so it lives on its own and is tested
hard. Mock and (later) Dentally both use it; Cliniko won't need it (it has an availability endpoint).
"""

from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional

from .models import Slot

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    """Two intervals overlap if each starts before the other ends."""
    return a_start < b_end and a_end > b_start


def compute_free_slots(config: dict, treatment_key: str, practitioner_id: Optional[str],
                       date_from: str, date_to: str, booked: List[dict],
                       now: Optional[datetime] = None,
                       granularity_min: int = 15, limit: int = 6,
                       time_from: Optional[str] = None,
                       time_to: Optional[str] = None) -> List[Slot]:
    tz = ZoneInfo(config["practice"]["timezone"])

    # Optional time-of-day window (e.g. caller wants the afternoon). A slot qualifies if its start is
    # at/after time_from and before time_to. Applied before the limit, so afternoon slots aren't lost.
    tod_from = _hhmm(time_from) if time_from else None
    tod_to = _hhmm(time_to) if time_to else None

    treatment = next((t for t in config["treatment_types"] if t["key"] == treatment_key), None)
    if treatment is None:
        raise ValueError(f"unknown treatment_key: {treatment_key}")
    duration = timedelta(minutes=treatment["duration_minutes"])
    step = timedelta(minutes=granularity_min)

    # Candidate practitioners: those who perform this treatment (optionally one specific).
    practitioners = [p for p in config["practitioners"] if treatment_key in p["treatment_keys"]]
    if practitioner_id is not None:
        practitioners = [p for p in practitioners if p["id"] == practitioner_id]

    d0 = date.fromisoformat(date_from)
    d1 = date.fromisoformat(date_to)

    slots: List[Slot] = []
    day = d0
    while day <= d1:
        weekday = WEEKDAYS[day.weekday()]
        for p in practitioners:
            # Per-practitioner working hours, falling back to practice opening hours.
            hours_map = p.get("working_hours") or config["opening_hours"]
            hours = hours_map.get(weekday)
            if not hours:
                continue  # day off / practice closed

            win_start = datetime.combine(day, _hhmm(hours["open"]), tz)
            win_end = datetime.combine(day, _hhmm(hours["close"]), tz)

            # Busy intervals for this practitioner today: breaks + their booked appointments.
            busy = []
            for b in hours.get("breaks", []):
                busy.append((datetime.combine(day, _hhmm(b["start"]), tz),
                             datetime.combine(day, _hhmm(b["end"]), tz)))
            for appt in booked:
                if appt["practitioner_id"] != p["id"]:
                    continue
                a_start = datetime.fromisoformat(appt["start"])
                a_end = datetime.fromisoformat(appt["end"])
                if a_start.astimezone(tz).date() == day:
                    busy.append((a_start, a_end))

            # Walk the day in fixed steps; a slot fits if it's inside the window,
            # not in the past, and doesn't overlap anything busy.
            t = win_start
            while t + duration <= win_end:
                s_start, s_end = t, t + duration
                tod = s_start.time()
                in_window = ((tod_from is None or tod >= tod_from)
                             and (tod_to is None or tod < tod_to))
                if in_window and (now is None or s_start >= now) and not any(
                        _overlaps(s_start, s_end, bs, be) for bs, be in busy):
                    slots.append(Slot(start=s_start.isoformat(),
                                      practitioner_id=p["id"],
                                      practitioner_name=p["name"]))
                t += step
        day += timedelta(days=1)

    slots.sort(key=lambda s: (s.start, s.practitioner_id))
    return slots[:limit]
