"""Tenant registry. Maps the dialled number (to_number) to that practice's config + its PMS.

In the mock phase there's one tenant, loaded from `seed_config.json` in this folder (so the backend
is self-contained and deploys cleanly on its own). It's keyed by the practice phone number.
Later this becomes a real lookup (Supabase) and each tenant points at its own PMS implementation.
"""

import json
import os

from pms.mock import MockPMS

# Self-contained seed lives next to this file (mirrors contracts/contract-1-example.json).
SEED_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_config.json")

# phone number dialled -> (config dict, PMS instance)
TENANTS = {}


def _init():
    with open(SEED_CONFIG) as f:
        cfg = json.load(f)
    TENANTS[cfg["practice"]["phone"]] = (cfg, MockPMS(cfg))   # MockPMS uses the real clock here


def get_tenant(to_number):
    """Return (config, pms) for the dialled number, or None if we don't serve it."""
    return TENANTS.get(to_number)


_init()
