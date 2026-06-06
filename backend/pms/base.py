"""The PMS interface (Contract 3). Every implementation (Mock, later Dentally/Cliniko)
subclasses this and provides the same five methods, returning the same shapes."""

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import Patient, Slot


class PMS(ABC):
    @abstractmethod
    def find_patient(self, first_name: str, last_name: str, dob: str) -> Optional[Patient]:
        """Return the patient (with upcoming appointments) or None."""

    @abstractmethod
    def create_patient(self, first_name: str, last_name: str, dob: str, phone: str) -> Patient:
        """Create and return a new patient."""

    @abstractmethod
    def get_available_slots(self, treatment_key: str, practitioner_id: Optional[str],
                            date_from: str, date_to: str) -> List[Slot]:
        """Free slots for the treatment in the date range. practitioner_id None = any."""

    @abstractmethod
    def create_appointment(self, patient_id: str, treatment_key: str,
                           practitioner_id: str, start: str) -> dict:
        """Book it. -> {"status": "booked", "appointment": {...}} or {"status": "slot_taken"}."""

    @abstractmethod
    def cancel_appointment(self, appointment_id: str) -> dict:
        """-> {"status": "cancelled"} or {"status": "not_found"}."""

    @abstractmethod
    def reschedule_appointment(self, appointment_id: str, new_start: str,
                               practitioner_id: Optional[str] = None) -> dict:
        """Move an appointment. -> {"status": "rescheduled", "appointment": {...}},
        {"status": "slot_taken"} (original kept), or {"status": "not_found"}."""
