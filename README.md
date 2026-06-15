# Voice Agent

A backend for an AI phone receptionist. A voice agent (Retell) answers a call, and this service
handles the real work behind it: checking availability, booking, looking up a caller, cancelling,
and rescheduling appointments.

It's multi-tenant (one deployment serves many practices, keyed by the dialled number) and
domain-agnostic — the same engine could run a dental practice, a garage, or a restaurant from one
config schema. The practice/PMS layer is swappable: a built-in `MockPMS` for development, or
`GoogleCalendarPMS` (Supabase for customers/bookings + Google Calendar for real times).

## How it works

```
   Caller ──phone──▶  Retell (voice AI: prompt + voice)
                          │  during the call: POST /webhook/<function>   (X-Webhook-Secret header)
                          ▼
                    FastAPI backend (this repo, on Railway)
                       1. find the practice by the dialled number     (tenants.py)
                       2. route the function to its handler            (handlers.py)
                       3. read/write via the PMS layer                 (pms/)
                       4. log the call                                 (db/)
                          │  small JSON result
                          ▼
                    Retell speaks the answer back to the caller

   when the call ends: Retell ──POST /webhook/call-event──▶ backend  (saves transcript + recording)
```

**Three systems:** **Railway** runs this backend · **Supabase** is the database (practice config,
customers, bookings, call logs) · **Google Calendar** is the source of truth for appointment *times*
(availability + the booking event). A booking is a real calendar event; Supabase keeps a reference to it.

## Endpoints

| Endpoint | Purpose | Auth |
|----------|---------|------|
| `POST /webhook/<function>` | the agent calls one of the 5 functions below | `X-Webhook-Secret` header |
| `POST /webhook/call-event` | Retell's end-of-call event → saves transcript/recording to `call_logs` | `?token=` in the URL |
| `GET /health` | uptime check | none |

## The 5 functions (the agent ↔ backend contract)

| Function | Send | Get back |
|----------|------|----------|
| `check_availability` | `treatment_key`, `date_from`, `date_to`; optional `practitioner_id`, `time_from`/`time_to` (`"HH:MM"`, for a part of the day) | `status` + `slots[]` (`start`, `practitioner_id`, `practitioner_name`) |
| `book_appointment` | `patient{first_name,last_name,dob,phone}`, `treatment_key`, `practitioner_id`, `start` | `booked` + `appointment_id`, or `slot_taken`, or `error` |
| `lookup_patient` | `first_name`, `last_name`, `dob` | `found` + `patient_id` + `upcoming[]`, or `not_found` |
| `cancel_appointment` | `appointment_id` | `cancelled` or `not_found` |
| `reschedule_appointment` | `appointment_id`, `new_start`; optional `practitioner_id` | `rescheduled` + `appointment_id`, or `slot_taken`, or `not_found` |

- Every reply has a `status` — the agent branches on it (only confirm on `booked`/`rescheduled`/`cancelled`).
- `appointment_id` is the Google Calendar event id (used for cancel/reschedule).
- Dates are `YYYY-MM-DD`; appointment times are the exact ISO strings the backend returns — never reformat them.
- Full detail per function is in `contracts/`.

## Configuration (per practice)

Each practice's settings — opening hours, practitioners (+ their calendar id), treatments, prices,
FAQ — live as one JSON document in the Supabase `tenants` table, keyed by the practice phone number.
`backend/seed_config.json` is an offline sample used when Supabase isn't configured (local/tests).

> Note: prices/FAQ the agent *speaks* come from the Retell **prompt**, not this config at runtime. If
> you change a price or hours, update both the config (what the backend computes from) and the prompt.

## Project layout

| Path | What it does |
|------|--------------|
| `backend/app.py` | FastAPI app — the `/webhook`, `/webhook/call-event`, `/health` endpoints |
| `backend/handlers.py` | One thin handler per agent function |
| `backend/tenants.py` | Resolves a practice (config + PMS) from the dialled number |
| `backend/pms/` | The PMS interface + `MockPMS` and `GoogleCalendarPMS` (+ the slot engine) |
| `backend/db/` | Supabase persistence (config, customers, bookings, call logs) + `schema.sql` |
| `contracts/` | The contracts between the agent and the backend |
| `COMPLIANCE.md` | Data-protection / GDPR notes |

## Run locally

```bash
cd backend
pip install -r requirements.txt
python3 app.py            # serves on http://127.0.0.1:8080
```

Out of the box it uses the sample config + `MockPMS`, so it just works with no setup — start here.
To run against real data/services, set these env vars:

| Variable | What it does |
|----------|--------------|
| `WEBHOOK_SECRET` | Locks the webhook so only our agent can call it. Always set this when deployed. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Read config + store customers/bookings/call logs in Supabase. |
| `GOOGLE_SERVICE_ACCOUNT_B64` | Use Google Calendar for real availability/bookings (`GoogleCalendarPMS`). |

Ask the team for these values — they live in our private notes, not in the repo.

Run the tests (plain scripts, no test runner needed):

```bash
python3 backend/test_pms.py
python3 backend/test_webhook.py
```

## Deploy

Hosted on Railway from this repo (auto-deploys on push to `main`). **Set the service Root Directory to
`backend`**, and add the env vars above as Railway variables. The start command + health check live in
`backend/railway.json`.
