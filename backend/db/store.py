"""Supabase persistence — a thin wrapper over the Supabase client.

The backend connects with the service_role key (server-side only; bypasses RLS).
A practice's whole Contract-1 config lives in the `tenants` table as a JSONB document.

If the SUPABASE_* env vars are absent (local dev / tests), the backend falls back to
the bundled seed_config.json instead of calling this module — see tenants.py.
"""

import os
from functools import lru_cache

from supabase import Client, create_client


def configured() -> bool:
    """True when Supabase env vars are present; else the backend uses the seed file."""
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


@lru_cache(maxsize=1)
def client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def fetch_tenant(phone_number: str):
    """The tenant row ({config, pms}) for a dialled number, or None if we don't serve it."""
    r = (client().table("tenants")
         .select("config, pms").eq("phone_number", phone_number).limit(1).execute())
    return r.data[0] if r.data else None


def upsert_tenant(config: dict, pms: str = "mock"):
    """Insert or update a practice's config row, keyed by the config's tenant_id."""
    row = {
        "id": config["tenant_id"],
        "phone_number": config["practice"]["phone"],
        "name": config["practice"]["name"],
        "pms": pms,
        "config": config,
    }
    return client().table("tenants").upsert(row).execute()


# ---- customers (returning-caller identity; Google Calendar has no patient concept) --------------
def find_customer(tenant_id: str, first_name: str, last_name: str, dob: str):
    """Match a returning caller by name + dob (case-insensitive), or None."""
    r = (client().table("customers").select("*")
         .eq("tenant_id", tenant_id)
         .ilike("first_name", first_name).ilike("last_name", last_name)
         .eq("dob", dob).limit(1).execute())
    return r.data[0] if r.data else None


def get_customer(tenant_id: str, customer_id: str):
    r = (client().table("customers").select("*")
         .eq("tenant_id", tenant_id).eq("id", customer_id).limit(1).execute())
    return r.data[0] if r.data else None


def create_customer(tenant_id: str, first_name: str, last_name: str, dob: str, phone: str):
    r = client().table("customers").insert({
        "tenant_id": tenant_id, "first_name": first_name, "last_name": last_name,
        "dob": dob, "phone": phone}).execute()
    return r.data[0]


# ---- bookings (a reference to a Google Calendar event + our metadata) ----------------------------
def create_booking(tenant_id: str, customer_id: str, gcal_calendar_id: str, gcal_event_id: str,
                   practitioner_id: str, treatment_key: str, starts_at: str, ends_at: str):
    r = client().table("bookings").insert({
        "tenant_id": tenant_id, "customer_id": customer_id,
        "gcal_calendar_id": gcal_calendar_id, "gcal_event_id": gcal_event_id,
        "practitioner_id": practitioner_id, "treatment_key": treatment_key,
        "starts_at": starts_at, "ends_at": ends_at}).execute()
    return r.data[0]


def get_booking_by_event(tenant_id: str, gcal_event_id: str):
    """The live (booked) booking row for a calendar event id, or None."""
    r = (client().table("bookings").select("*")
         .eq("tenant_id", tenant_id).eq("gcal_event_id", gcal_event_id)
         .eq("status", "booked").limit(1).execute())
    return r.data[0] if r.data else None


def update_booking(booking_id: str, fields: dict):
    return client().table("bookings").update(fields).eq("id", booking_id).execute()


def list_upcoming_bookings(tenant_id: str, customer_id: str, now_iso: str):
    r = (client().table("bookings").select("*")
         .eq("tenant_id", tenant_id).eq("customer_id", customer_id)
         .eq("status", "booked").gte("starts_at", now_iso)
         .order("starts_at").execute())
    return r.data
