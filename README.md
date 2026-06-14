# Voice Agent

A backend for an AI phone receptionist. A voice agent (Retell) answers a call, and this service
handles the real work behind it: checking availability, booking, looking up a caller, cancelling,
and rescheduling appointments.

It's multi-tenant (one deployment serves many practices, keyed by the dialled number) and
domain-agnostic — the same engine runs a dental practice, a garage, or a restaurant from one config
schema. The practice/PMS layer is swappable: a built-in `MockPMS` for development, or
`GoogleCalendarPMS` (Supabase for customers/bookings + Google Calendar for real times).

## High-level workflow

```
   Caller ──phone──▶  Retell (voice AI)
                          │  POST /webhook  (X-Webhook-Secret)
                          ▼
                    FastAPI backend (this repo)
                          │
        1. find the practice by the dialled number   (tenants.py)
        2. route the function to its handler          (handlers.py)
        3. call the PMS                                (pms/)
        4. log the call                               (db/)
                          │  JSON result
                          ▼
                    Retell speaks the answer back to the caller
```

The five functions the agent can call: `check_availability`, `book_appointment`,
`lookup_patient`, `cancel_appointment`, `reschedule_appointment`.

## Project layout

| Path | What it does |
|------|--------------|
| `backend/app.py` | FastAPI app — the `/webhook` and `/health` endpoints |
| `backend/handlers.py` | One thin handler per agent function |
| `backend/tenants.py` | Resolves a practice (config + PMS) from the dialled number |
| `backend/pms/` | The PMS interface + `MockPMS` and `GoogleCalendarPMS` |
| `backend/db/` | Supabase persistence (config, customers, bookings, call logs) |
| `contracts/` | The frozen contracts between the agent and the backend |
| `COMPLIANCE.md` | Data-protection / GDPR notes |

## Run locally

```bash
cd backend
pip install -r requirements.txt
python3 app.py            # serves on http://127.0.0.1:8080
```

With no env vars set it runs **open** (no auth) against the seed config + `MockPMS` — good for dev.
Set `WEBHOOK_SECRET` (and the `SUPABASE_*` vars for real persistence) on any deployed instance.

Run the tests (plain scripts, no test runner needed):

```bash
python3 backend/test_pms.py
python3 backend/test_webhook.py
```
