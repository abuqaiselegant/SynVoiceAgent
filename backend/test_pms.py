"""Exercises MockPMS + the slot engine against the dental example config.

Run: python3 backend/test_pms.py
Deterministic: pins 'now' to Monday 2026-06-08 08:00 BST so results don't depend on the clock.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pms.mock import MockPMS               # noqa: E402
from pms.slots import compute_free_slots   # noqa: E402

CONFIG = json.load(open(os.path.join(HERE, "..", "contracts", "contract-1-example.json")))
TZ = ZoneInfo(CONFIG["practice"]["timezone"])

JANE = "dentally_practitioner_101"   # Dentist: exam, scale_polish, filling, emergency. Mon/Wed/Thu/Fri
AISHA = "dentally_practitioner_102"  # Hygienist: scale_polish. Tue/Thu/Fri/Sat

results = []


def check(name, cond):
    results.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


def iso(s):
    return datetime.fromisoformat(s)


def overlaps(s, dur_min, a, b):
    st = iso(s.start)
    return st < iso(b) and st + timedelta(minutes=dur_min) > iso(a)


def main():
    now = datetime(2026, 6, 8, 8, 0, tzinfo=TZ)   # Monday 08:00
    pms = MockPMS(CONFIG, now=now)

    # --- patients --------------------------------------------------------
    check("unknown patient -> None", pms.find_patient("John", "Doe", "1985-03-22") is None)
    john = pms.create_patient("John", "Doe", "1985-03-22", "+447700900123")
    check("create_patient gives an id", john.id.startswith("pat_"))

    # --- seed a booking: exam with Jane, Monday 10:00 --------------------
    r = pms.create_appointment(john.id, "exam", JANE, "2026-06-08T10:00:00+01:00")
    check("seed booking -> booked", r["status"] == "booked")
    check("exam end is +20 min", r["appointment"]["end"] == "2026-06-08T10:20:00+01:00")
    seeded_id = r["appointment"]["id"]

    found = pms.find_patient("john", "doe", "1985-03-22")   # case-insensitive
    check("find_patient finds (case-insensitive)", found and found.id == john.id)
    check("upcoming shows the seeded appt",
          len(found.upcoming) == 1 and found.upcoming[0]["id"] == seeded_id)

    # --- availability: exam (only Jane does exam) ------------------------
    slots = pms.get_available_slots("exam", None, "2026-06-08", "2026-06-12")
    mon = [s for s in slots if s.start.startswith("2026-06-08")]
    check("exam slots returned", len(slots) > 0)
    check("all exam slots are Jane", all(s.practitioner_id == JANE for s in slots))
    check("no slot before now (08:00)", all(iso(s.start) >= now for s in slots))
    check("no exam slot overlaps the 10:00 booking",
          not any(overlaps(s, 20, "2026-06-08T10:00:00+01:00", "2026-06-08T10:20:00+01:00") for s in mon))
    check("no exam slot overlaps Monday lunch 13:00-14:00",
          not any(overlaps(s, 20, "2026-06-08T13:00:00+01:00", "2026-06-08T14:00:00+01:00") for s in mon))
    check("09:00 Monday is offered (free before the 10:00 booking)",
          any(s.start == "2026-06-08T09:00:00+01:00" for s in slots))

    # --- cross-day / multi-practitioner (raise the limit to see the week)
    sp = compute_free_slots(CONFIG, "scale_polish", None, "2026-06-08", "2026-06-13",
                            [a.to_dict() for a in pms._booked()], now=now, limit=100000)
    pset = {s.practitioner_id for s in sp}
    check("scale_polish offered by BOTH Jane and Aisha across the week",
          JANE in pset and AISHA in pset)
    check("Aisha has no Monday slot (she's off Mon)",
          not any(s.practitioner_id == AISHA and s.start.startswith("2026-06-08") for s in sp))
    check("Jane has no Tuesday slot (she's off Tue)",
          not any(s.practitioner_id == JANE and s.start.startswith("2026-06-09") for s in sp))

    # --- practitioner-specific query ------------------------------------
    aisha_tue = compute_free_slots(CONFIG, "scale_polish", AISHA, "2026-06-09", "2026-06-09",
                                   [a.to_dict() for a in pms._booked()], now=now, limit=100000)
    check("practitioner filter returns only Aisha, and some slots",
          len(aisha_tue) > 0 and all(s.practitioner_id == AISHA for s in aisha_tue))

    # --- booking races ---------------------------------------------------
    r2 = pms.create_appointment(john.id, "exam", JANE, "2026-06-08T09:00:00+01:00")
    check("book 09:00 -> booked", r2["status"] == "booked")
    r3 = pms.create_appointment(john.id, "exam", JANE, "2026-06-08T09:00:00+01:00")
    check("re-book same slot -> slot_taken", r3["status"] == "slot_taken")
    r4 = pms.create_appointment(john.id, "exam", JANE, "2026-06-08T09:10:00+01:00")
    check("overlapping booking -> slot_taken", r4["status"] == "slot_taken")

    after = pms.get_available_slots("exam", None, "2026-06-08", "2026-06-12")
    check("09:00 no longer offered after it's booked",
          not any(s.start == "2026-06-08T09:00:00+01:00" for s in after))

    # --- cancel ----------------------------------------------------------
    check("cancel booked -> cancelled",
          pms.cancel_appointment(r2["appointment"]["id"])["status"] == "cancelled")
    check("cancel again -> not_found",
          pms.cancel_appointment(r2["appointment"]["id"])["status"] == "not_found")
    check("cancel unknown id -> not_found",
          pms.cancel_appointment("appt_nope")["status"] == "not_found")

    freed = pms.get_available_slots("exam", None, "2026-06-08", "2026-06-12")
    check("09:00 offered again after cancel",
          any(s.start == "2026-06-08T09:00:00+01:00" for s in freed))

    # --- bad input -------------------------------------------------------
    try:
        pms.get_available_slots("nonexistent", None, "2026-06-08", "2026-06-12")
        check("unknown treatment raises ValueError", False)
    except ValueError:
        check("unknown treatment raises ValueError", True)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
