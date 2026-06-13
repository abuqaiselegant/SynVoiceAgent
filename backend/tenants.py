"""Tenant registry. Maps the dialled number (to_number) to that practice's config + its PMS.

With Supabase configured, the config is read from the `tenants` table (keyed by the practice
phone number) and cached per number for the life of the process. Without Supabase env vars
(local dev / tests), it falls back to the bundled `seed_config.json` so the backend stays
self-contained and the tests run offline.
"""

import json
import os

from pms.mock import MockPMS
from db import store

# Self-contained seed lives next to this file (mirrors contracts/contract-1-example.json).
SEED_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_config.json")

# phone number dialled -> (config dict, PMS instance). Cached after first lookup.
TENANTS = {}


def _make_pms(config, pms_name):
    if pms_name == "mock":
        return MockPMS(config)   # MockPMS uses the real clock here
    raise ValueError(f"PMS '{pms_name}' is not implemented yet")


def _load_tenant(to_number):
    """Build (config, pms) for a dialled number from Supabase, or the seed file if unconfigured."""
    if store.configured():
        row = store.fetch_tenant(to_number)
        if row is None:
            return None
        return (row["config"], _make_pms(row["config"], row["pms"]))

    with open(SEED_CONFIG) as f:
        cfg = json.load(f)
    if cfg["practice"]["phone"] != to_number:
        return None
    return (cfg, MockPMS(cfg))


def get_tenant(to_number):
    """Return (config, pms) for the dialled number, or None if we don't serve it."""
    if to_number not in TENANTS:
        result = _load_tenant(to_number)
        if result is None:
            return None
        TENANTS[to_number] = result
    return TENANTS[to_number]
