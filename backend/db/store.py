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
