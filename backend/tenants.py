"""Tenant registry. Maps the dialled number (to_number) to that practice's config + its PMS.

In the mock phase there's one tenant: the dental example config, keyed by its practice phone.
Later this becomes a real lookup (Supabase) and each tenant points at its own PMS implementation.
"""

import json
import os

from pms.mock import MockPMS

CONTRACTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "contracts")

# phone number dialled -> (config dict, PMS instance)
TENANTS = {}


def _load_config(filename):
    with open(os.path.join(CONTRACTS_DIR, filename)) as f:
        return json.load(f)


def _init():
    cfg = _load_config("contract-1-example.json")          # the dental example practice
    TENANTS[cfg["practice"]["phone"]] = (cfg, MockPMS(cfg))  # MockPMS uses the real clock here


def get_tenant(to_number):
    """Return (config, pms) for the dialled number, or None if we don't serve it."""
    return TENANTS.get(to_number)


_init()
