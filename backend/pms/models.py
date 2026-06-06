"""Data shapes returned by the PMS layer. These match Contract 3 exactly."""

from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class Slot:
    start: str               # ISO 8601 with offset, e.g. "2026-06-10T14:00:00+01:00"
    practitioner_id: str
    practitioner_name: str

    def to_dict(self):
        return asdict(self)


@dataclass
class Appointment:
    id: str
    start: str
    end: str
    treatment_key: str
    treatment_name: str
    practitioner_id: str
    practitioner_name: str
    status: str = "booked"   # "booked" | "cancelled"

    def to_dict(self):
        return asdict(self)


@dataclass
class Patient:
    id: str
    first_name: str
    last_name: str
    dob: str                 # "YYYY-MM-DD"
    phone: str
    upcoming: List[dict] = field(default_factory=list)  # list of Appointment dicts

    def to_dict(self):
        return asdict(self)
