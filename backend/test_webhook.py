"""Exercises the webhook handlers (the dispatch layer) end to end against MockPMS.

Goes through a realistic call flow: check availability -> book -> look up -> reschedule -> cancel,
asserting each response matches the Contract 2 shape. No HTTP server needed (dispatch is pure).

Run: python3 backend/test_webhook.py
Deterministic: pins 'now' to Monday 2026-06-08 08:00 BST.
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pms.mock import MockPMS   # noqa: E402
from handlers import dispatch  # noqa: E402

CONFIG = json.load(open(os.path.join(HERE, "seed_config.json")))
TZ = ZoneInfo(CONFIG["practice"]["timezone"])
JANE = "dentally_practitioner_101"

results = []


def check(name, cond):
    results.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


def main():
    pms = MockPMS(CONFIG, now=datetime(2026, 6, 8, 8, 0, tzinfo=TZ))

    # 1. check_availability
    avail = dispatch(pms, "check_availability",
                     {"treatment_key": "exam", "practitioner_id": None,
                      "date_from": "2026-06-08", "date_to": "2026-06-12"})
    check("check_availability -> ok", avail["status"] == "ok")
    check("returns slots with the right keys",
          avail["slots"] and set(avail["slots"][0]) == {"start", "practitioner_id", "practitioner_name"})
    first_slot = avail["slots"][0]

    # 2. book_appointment at the first offered slot
    book = dispatch(pms, "book_appointment",
                    {"patient": {"first_name": "John", "last_name": "Doe",
                                 "dob": "1985-03-22", "phone": "+447700900123"},
                     "treatment_key": "exam", "practitioner_id": first_slot["practitioner_id"],
                     "start": first_slot["start"]})
    check("book_appointment -> booked", book["status"] == "booked")
    check("book returns an appointment_id", book.get("appointment_id", "").startswith("appt_"))

    # 3. booking the same slot again -> slot_taken
    book2 = dispatch(pms, "book_appointment",
                     {"patient": {"first_name": "John", "last_name": "Doe",
                                  "dob": "1985-03-22", "phone": "+447700900123"},
                      "treatment_key": "exam", "practitioner_id": first_slot["practitioner_id"],
                      "start": first_slot["start"]})
    check("re-book same slot -> slot_taken", book2["status"] == "slot_taken")

    # 4. lookup_patient -> finds John + his upcoming appt in Contract 2 shape
    look = dispatch(pms, "lookup_patient",
                    {"first_name": "John", "last_name": "Doe", "dob": "1985-03-22"})
    check("lookup_patient -> found", look["status"] == "found")
    check("upcoming has Contract 2 keys",
          look["upcoming"] and set(look["upcoming"][0]) ==
          {"appointment_id", "start", "treatment", "practitioner_name"})
    appt_id = look["upcoming"][0]["appointment_id"]

    # 5. reschedule to a different free slot
    avail2 = dispatch(pms, "check_availability",
                      {"treatment_key": "exam", "practitioner_id": JANE,
                       "date_from": "2026-06-08", "date_to": "2026-06-12"})
    new_slot = next(s for s in avail2["slots"] if s["start"] != first_slot["start"])
    resched = dispatch(pms, "reschedule_appointment",
                       {"appointment_id": appt_id, "new_start": new_slot["start"]})
    check("reschedule_appointment -> rescheduled", resched["status"] == "rescheduled")
    new_appt_id = resched["appointment_id"]
    check("reschedule returns a new appointment_id", new_appt_id != appt_id)

    # 6. lookup reflects the new time, old id gone
    look2 = dispatch(pms, "lookup_patient",
                     {"first_name": "John", "last_name": "Doe", "dob": "1985-03-22"})
    ids = {a["appointment_id"] for a in look2["upcoming"]}
    check("upcoming now shows the new appointment", new_appt_id in ids and appt_id not in ids)

    # 7. cancel the new appointment, then cancel again -> not_found
    check("cancel_appointment -> cancelled",
          dispatch(pms, "cancel_appointment", {"appointment_id": new_appt_id})["status"] == "cancelled")
    check("cancel again -> not_found",
          dispatch(pms, "cancel_appointment", {"appointment_id": new_appt_id})["status"] == "not_found")

    # 8. unknown function + bad args -> safe error
    check("unknown function -> error",
          dispatch(pms, "make_coffee", {})["status"] == "error")
    check("missing args -> error",
          dispatch(pms, "check_availability", {})["status"] == "error")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
