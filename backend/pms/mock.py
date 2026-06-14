"""MockPMS — an in-memory implementation of the PMS interface. No external account.

Stores patients and appointments in dicts. get_available_slots runs the real slot engine against
the config, so the hard part is exercised for real — just with made-up bookings. We can force any
case for testing (no slots, a slot_taken race, an existing patient). When a real PMS arrives it
slots in behind the same interface and nothing else changes.
"""

import itertools
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional

from .base import PMS
from .models import Patient, Appointment, Slot
from .slots import compute_free_slots, _overlaps


class MockPMS(PMS):
    def __init__(self, config: dict, now: Optional[datetime] = None):
        self.config = config
        self.tz = ZoneInfo(config["practice"]["timezone"])
        self.now = now                       # if set, hides past slots / past appointments
        self.patients = {}                   # id -> Patient
        self.appointments = {}               # id -> Appointment
        self.appt_owner = {}                 # appointment id -> patient id
        self._next_pid = itertools.count(1)
        self._next_aid = itertools.count(1)

    # --- internal helpers -------------------------------------------------
    def _treatment(self, key: str) -> dict:
        t = next((t for t in self.config["treatment_types"] if t["key"] == key), None)
        if t is None:
            raise ValueError(f"unknown treatment_key: {key}")
        return t

    def _practitioner(self, pid: str) -> dict:
        p = next((p for p in self.config["practitioners"] if p["id"] == pid), None)
        if p is None:
            raise ValueError(f"unknown practitioner_id: {pid}")
        return p

    def _booked(self) -> List[Appointment]:
        return [a for a in self.appointments.values() if a.status == "booked"]

    def _upcoming_for(self, patient_id: str) -> List[dict]:
        out = []
        for aid, appt in self.appointments.items():
            if self.appt_owner.get(aid) == patient_id and appt.status == "booked":
                if self.now is None or datetime.fromisoformat(appt.start) >= self.now:
                    out.append(appt.to_dict())
        out.sort(key=lambda a: a["start"])
        return out

    # --- interface (Contract 3) ------------------------------------------
    # Find an existing patient by name + date of birth (case-insensitive).
    def find_patient(self, first_name: str, last_name: str, dob: str) -> Optional[Patient]:
        for p in self.patients.values():
            if (p.first_name.lower() == first_name.lower()
                    and p.last_name.lower() == last_name.lower()
                    and p.dob == dob):
                p.upcoming = self._upcoming_for(p.id)
                return p
        return None

    # Register a brand-new patient.
    def create_patient(self, first_name: str, last_name: str, dob: str, phone: str) -> Patient:
        pid = f"pat_{next(self._next_pid)}"
        patient = Patient(id=pid, first_name=first_name, last_name=last_name,
                          dob=dob, phone=phone, upcoming=[])
        self.patients[pid] = patient
        return patient

    # Ask the slot engine for free times, given everything currently booked.
    def get_available_slots(self, treatment_key: str, practitioner_id: Optional[str],
                            date_from: str, date_to: str,
                            time_from: Optional[str] = None,
                            time_to: Optional[str] = None) -> List[Slot]:
        booked = [a.to_dict() for a in self._booked()]
        return compute_free_slots(self.config, treatment_key, practitioner_id,
                                  date_from, date_to, booked, now=self.now,
                                  time_from=time_from, time_to=time_to)

    # Book an appointment, guarding against two callers grabbing the same slot.
    def create_appointment(self, patient_id: str, treatment_key: str,
                           practitioner_id: str, start: str) -> dict:
        treatment = self._treatment(treatment_key)
        practitioner = self._practitioner(practitioner_id)
        start_dt = datetime.fromisoformat(start)
        end_dt = start_dt + timedelta(minutes=treatment["duration_minutes"])

        # Re-check at write time: never confirm a booking that collides with a live one.
        for a in self._booked():
            if a.practitioner_id != practitioner_id:
                continue
            if _overlaps(start_dt, end_dt, datetime.fromisoformat(a.start),
                         datetime.fromisoformat(a.end)):
                return {"status": "slot_taken"}

        aid = f"appt_{next(self._next_aid)}"
        appt = Appointment(id=aid, start=start_dt.isoformat(), end=end_dt.isoformat(),
                           treatment_key=treatment_key, treatment_name=treatment["name"],
                           practitioner_id=practitioner_id, practitioner_name=practitioner["name"],
                           status="booked")
        self.appointments[aid] = appt
        self.appt_owner[aid] = patient_id
        return {"status": "booked", "appointment": appt.to_dict()}

    # Cancel an appointment by id (marks it cancelled so its slot frees up again).
    def cancel_appointment(self, appointment_id: str) -> dict:
        appt = self.appointments.get(appointment_id)
        if appt is None or appt.status != "booked":
            return {"status": "not_found"}
        appt.status = "cancelled"
        return {"status": "cancelled"}

    # Move an appointment to a new time. Checks the new slot first; if it's taken we keep the
    # original untouched. Otherwise we cancel the old one and create the new one (same patient +
    # treatment, optionally a different practitioner).
    def reschedule_appointment(self, appointment_id: str, new_start: str,
                               practitioner_id: Optional[str] = None) -> dict:
        appt = self.appointments.get(appointment_id)
        if appt is None or appt.status != "booked":
            return {"status": "not_found"}

        patient_id = self.appt_owner.get(appointment_id)
        treatment = self._treatment(appt.treatment_key)
        target_practitioner = practitioner_id or appt.practitioner_id
        practitioner = self._practitioner(target_practitioner)
        start_dt = datetime.fromisoformat(new_start)
        end_dt = start_dt + timedelta(minutes=treatment["duration_minutes"])

        # Re-check the new slot, ignoring the very appointment we're moving.
        for a in self._booked():
            if a.id == appointment_id or a.practitioner_id != target_practitioner:
                continue
            if _overlaps(start_dt, end_dt, datetime.fromisoformat(a.start),
                         datetime.fromisoformat(a.end)):
                return {"status": "slot_taken"}   # original booking left intact

        appt.status = "cancelled"                  # release the old time
        aid = f"appt_{next(self._next_aid)}"
        new_appt = Appointment(id=aid, start=start_dt.isoformat(), end=end_dt.isoformat(),
                               treatment_key=appt.treatment_key, treatment_name=treatment["name"],
                               practitioner_id=target_practitioner,
                               practitioner_name=practitioner["name"], status="booked")
        self.appointments[aid] = new_appt
        self.appt_owner[aid] = patient_id
        return {"status": "rescheduled", "appointment": new_appt.to_dict()}
