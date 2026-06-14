"""GoogleCalendarPMS — the Contract 3 interface backed by Supabase + Google Calendar.

Split of responsibilities:
  * Customers (returning-caller identity) live in Supabase — a calendar has no patient concept.
  * The appointment TIME lives in Google Calendar: free/busy is the source of availability, and a
    booking is a real calendar event. We keep only a *reference* (the event id) in Supabase `bookings`.

The appointment id handed back to the agent is the Google Calendar event id, so cancel/reschedule
resolve straight to the event.

Practitioners are mapped to calendars by a `calendar_id` field on each practitioner in config; a
practitioner without one is simply not bookable yet (e.g. Aisha until her calendar is shared).
"""

import base64
import json
import os
from datetime import datetime, date, time, timedelta, timezone
from functools import lru_cache
from typing import List, Optional
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .base import PMS
from .models import Patient, Appointment, Slot
from .slots import compute_free_slots, _overlaps
from db import store

SCOPES = ["https://www.googleapis.com/auth/calendar"]


@lru_cache(maxsize=1)
def _service():
    """The Google Calendar API client, built from the base64 service-account key in the env."""
    info = json.loads(base64.b64decode(os.environ["GOOGLE_SERVICE_ACCOUNT_B64"]))
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


class GoogleCalendarPMS(PMS):
    def __init__(self, config: dict, now: Optional[datetime] = None):
        self.config = config
        self.tenant_id = config["tenant_id"]
        self.tz_name = config["practice"]["timezone"]
        self.tz = ZoneInfo(self.tz_name)
        self.now = now or datetime.now(self.tz)
        self.svc = _service()

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

    def _local(self, dt: datetime) -> str:
        """ISO timestamp in the practice timezone (what the agent reads back)."""
        return dt.astimezone(self.tz).isoformat()

    def _customer_name(self, customer_id: str) -> str:
        c = store.get_customer(self.tenant_id, customer_id)
        return f"{c['first_name']} {c['last_name']}" if c else "Patient"

    def _slot_is_free(self, calendar_id: str, start_dt: datetime, end_dt: datetime,
                      exclude_event_id: Optional[str] = None) -> bool:
        """Write-time re-check on a single calendar window, excluding one event (for reschedule)."""
        r = self.svc.events().list(
            calendarId=calendar_id,
            timeMin=start_dt.astimezone(timezone.utc).isoformat(),
            timeMax=end_dt.astimezone(timezone.utc).isoformat(),
            singleEvents=True).execute()
        for ev in r.get("items", []):
            if ev["id"] == exclude_event_id or ev.get("status") == "cancelled":
                continue
            s, e = ev["start"].get("dateTime"), ev["end"].get("dateTime")
            if not s or not e:
                continue  # all-day / open-ended event — ignore
            if _overlaps(start_dt, end_dt, datetime.fromisoformat(s), datetime.fromisoformat(e)):
                return False
        return True

    def _book_event(self, calendar_id: str, treatment: dict, name: str,
                    start_dt: datetime, end_dt: datetime) -> str:
        ev = self.svc.events().insert(calendarId=calendar_id, body={
            "summary": f"{treatment['name']} — {name}",
            "start": {"dateTime": start_dt.isoformat(), "timeZone": self.tz_name},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": self.tz_name},
        }).execute()
        return ev["id"]

    def _delete_event(self, calendar_id: str, event_id: str):
        try:
            self.svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        except HttpError as e:
            if e.resp.status not in (404, 410):  # already gone is fine
                raise

    # --- interface (Contract 3) ------------------------------------------
    def find_patient(self, first_name: str, last_name: str, dob: str) -> Optional[Patient]:
        cust = store.find_customer(self.tenant_id, first_name, last_name, dob)
        if cust is None:
            return None
        now_iso = self.now.astimezone(timezone.utc).isoformat()
        upcoming = [{
            "id": b["gcal_event_id"],
            "start": self._local(datetime.fromisoformat(b["starts_at"])),
            "treatment_name": self._treatment(b["treatment_key"])["name"],
            "practitioner_name": self._practitioner(b["practitioner_id"])["name"],
        } for b in store.list_upcoming_bookings(self.tenant_id, cust["id"], now_iso)]
        return Patient(id=cust["id"], first_name=cust["first_name"], last_name=cust["last_name"],
                       dob=str(cust["dob"]), phone=cust.get("phone") or "", upcoming=upcoming)

    def create_patient(self, first_name: str, last_name: str, dob: str, phone: str) -> Patient:
        c = store.create_customer(self.tenant_id, first_name, last_name, dob, phone)
        return Patient(id=c["id"], first_name=c["first_name"], last_name=c["last_name"],
                       dob=str(c["dob"]), phone=c.get("phone") or "", upcoming=[])

    def get_available_slots(self, treatment_key: str, practitioner_id: Optional[str],
                            date_from: str, date_to: str,
                            time_from: Optional[str] = None,
                            time_to: Optional[str] = None) -> List[Slot]:
        # Only practitioners with a shared calendar are bookable; restrict the config we hand the
        # slot engine to those, so it never offers a practitioner we can't actually book.
        cal_practitioners = [p for p in self.config["practitioners"] if p.get("calendar_id")]
        if practitioner_id is not None:
            cal_practitioners = [p for p in cal_practitioners if p["id"] == practitioner_id]

        time_min = datetime.combine(date.fromisoformat(date_from), time(0, 0), self.tz)
        time_max = datetime.combine(date.fromisoformat(date_to), time(23, 59, 59), self.tz)

        booked = []
        for p in cal_practitioners:
            fb = self.svc.freebusy().query(body={
                "timeMin": time_min.isoformat(), "timeMax": time_max.isoformat(),
                "items": [{"id": p["calendar_id"]}],
            }).execute()
            for b in fb["calendars"][p["calendar_id"]].get("busy", []):
                booked.append({"practitioner_id": p["id"], "start": b["start"], "end": b["end"]})

        cfg = {**self.config, "practitioners": cal_practitioners}
        return compute_free_slots(cfg, treatment_key, practitioner_id,
                                  date_from, date_to, booked, now=self.now,
                                  time_from=time_from, time_to=time_to)

    def create_appointment(self, patient_id: str, treatment_key: str,
                           practitioner_id: str, start: str) -> dict:
        treatment = self._treatment(treatment_key)
        practitioner = self._practitioner(practitioner_id)
        calendar_id = practitioner.get("calendar_id")
        if not calendar_id:
            return {"status": "error"}  # practitioner has no calendar yet

        start_dt = datetime.fromisoformat(start)
        end_dt = start_dt + timedelta(minutes=treatment["duration_minutes"])
        if not self._slot_is_free(calendar_id, start_dt, end_dt):
            return {"status": "slot_taken"}

        event_id = self._book_event(calendar_id, treatment, self._customer_name(patient_id),
                                    start_dt, end_dt)
        store.create_booking(self.tenant_id, patient_id, calendar_id, event_id,
                             practitioner_id, treatment_key,
                             start_dt.isoformat(), end_dt.isoformat())
        appt = Appointment(id=event_id, start=self._local(start_dt), end=self._local(end_dt),
                           treatment_key=treatment_key, treatment_name=treatment["name"],
                           practitioner_id=practitioner_id, practitioner_name=practitioner["name"])
        return {"status": "booked", "appointment": appt.to_dict()}

    def cancel_appointment(self, appointment_id: str) -> dict:
        booking = store.get_booking_by_event(self.tenant_id, appointment_id)
        if booking is None:
            return {"status": "not_found"}
        self._delete_event(booking["gcal_calendar_id"], appointment_id)
        store.update_booking(booking["id"], {"status": "cancelled"})
        return {"status": "cancelled"}

    def reschedule_appointment(self, appointment_id: str, new_start: str,
                               practitioner_id: Optional[str] = None) -> dict:
        booking = store.get_booking_by_event(self.tenant_id, appointment_id)
        if booking is None:
            return {"status": "not_found"}

        treatment = self._treatment(booking["treatment_key"])
        target_pid = practitioner_id or booking["practitioner_id"]
        practitioner = self._practitioner(target_pid)
        calendar_id = practitioner.get("calendar_id")
        if not calendar_id:
            return {"status": "error"}

        start_dt = datetime.fromisoformat(new_start)
        end_dt = start_dt + timedelta(minutes=treatment["duration_minutes"])
        # Ignore the event we're moving only when checking its own calendar.
        exclude = appointment_id if calendar_id == booking["gcal_calendar_id"] else None
        if not self._slot_is_free(calendar_id, start_dt, end_dt, exclude_event_id=exclude):
            return {"status": "slot_taken"}  # original left intact

        self._delete_event(booking["gcal_calendar_id"], appointment_id)
        event_id = self._book_event(calendar_id, treatment,
                                    self._customer_name(booking["customer_id"]), start_dt, end_dt)
        store.update_booking(booking["id"], {
            "gcal_calendar_id": calendar_id, "gcal_event_id": event_id,
            "practitioner_id": target_pid,
            "starts_at": start_dt.isoformat(), "ends_at": end_dt.isoformat()})
        appt = Appointment(id=event_id, start=self._local(start_dt), end=self._local(end_dt),
                           treatment_key=booking["treatment_key"], treatment_name=treatment["name"],
                           practitioner_id=target_pid, practitioner_name=practitioner["name"])
        return {"status": "rescheduled", "appointment": appt.to_dict()}
