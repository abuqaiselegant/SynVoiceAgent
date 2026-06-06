# Contract 2 — Webhook Payload

**Status:** DRAFT v1 — 2026-06-06
**Owner:** Person A (defines the shapes & implements the backend) · Person B (configures the Retell
agent's function calls against these exact names & params)

This is the wire between the voice agent (Retell) and the backend. It defines, per intent, exactly
what Retell POSTs to the backend during a call and exactly what the backend returns. The agent
reads the response and decides what to say. Worked examples:
[`contract-2-examples.json`](./contract-2-examples.json).

---

## Design rules (read first)

1. **Function names & arg keys are frozen once shared.** B builds the Retell agent against these
   strings. Renaming a function or an arg key breaks the agent silently. Change = tell B first.
2. **`status` is the real contract.** Every response carries a `status` string from a fixed set per
   function. The agent branches on it. These exact words matter more than anything else here.
3. **The agent only acts as confirmed on a success status.** It may only tell the caller "you're
   booked" on `booked` (or "moved" on `rescheduled`). Any other status = don't confirm.
4. **Always answer, never hang.** On any unexpected failure the backend returns
   `{"status": "error", "message": "..."}` so the agent can fall back (take a message / transfer)
   rather than leaving dead air.
5. **One tenant per call, derived from `to_number`.** The backend maps the dialled number to a
   practice config. The agent never sends a tenant id.
6. **Times are ISO 8601 with offset**, in the practice's timezone (e.g. `2026-06-10T14:00:00+01:00`).

---

## What needs the backend vs. what doesn't

The agent calls the backend for **five things**. Everything else is static text in the agent's
prompt, filled from config (Contract 1) — no webhook round-trip.

| function | when the agent calls it | reads from |
|----------|------------------------|------------|
| `check_availability`     | caller wants to book / reschedule — find free slots | slot engine |
| `book_appointment`       | caller picked a slot — make the booking | PMS layer |
| `lookup_patient`         | for cancel/reschedule — find caller + their appointments | PMS layer |
| `cancel_appointment`     | caller wants to cancel | PMS layer |
| `reschedule_appointment` | caller wants to move an appointment (cancel + rebook) | PMS layer |
| *FAQ*                    | caller asks a known question | **prompt** (config `faq`) — no call |
| *out-of-hours greeting* | call lands outside opening hours | **prompt** (config hours) — no call |

---

## Common request envelope (every function)

```jsonc
{
  "call_id": "retell_abc123",      // string, required. Retell's call id — we log against it.
  "to_number": "+441162345678",    // E.164, required. Number dialled -> identifies the tenant.
  "from_number": "+447700900123",  // E.164, required. Caller's number -> SMS + patient match hint.
  "function": "check_availability",// string, required. Which of the five intents this is.
  "args": { /* function-specific, below */ }   // object, required.
}
```
> Retell's real payload nests these fields differently depending on Retell's version. The backend
> reads Retell's actual request and maps it onto this envelope. These five keys are the ones that
> matter to our logic — define everything else as "whatever Retell sends, ignored."

## Common response envelope (every function)

```jsonc
{
  "status": "ok",                       // string, required. Fixed set per function (below).
  "message": "I found a few times.",    // string, optional. A short human line the agent MAY speak.
  /* ...plus function-specific data */
}
```
The agent decides what to say from `status` + the data; `message` is only a convenience fallback.

---

## Intents

### 1. `check_availability`
**args**
```jsonc
{
  "treatment_key": "exam",        // string, required. A treatment_types.key from config.
  "practitioner_id": null,        // string | null. null = any practitioner who does this treatment.
  "date_from": "2026-06-10",      // "YYYY-MM-DD", required. Earliest date the caller wants.
  "date_to": "2026-06-14"         // "YYYY-MM-DD", required. Latest date. Backend caps the range.
}
```
**response** — `status` ∈ { `ok`, `no_slots` }
```jsonc
{
  "status": "ok",
  "slots": [
    { "start": "2026-06-10T14:00:00+01:00", "practitioner_id": "dentally_practitioner_101", "practitioner_name": "Dr. Jane Smith" },
    { "start": "2026-06-10T15:30:00+01:00", "practitioner_id": "dentally_practitioner_101", "practitioner_name": "Dr. Jane Smith" }
  ]
}
```
- Backend returns a **small handful** of slots (not hundreds) — enough for the agent to offer 2–3.
- `no_slots` = nothing free in range; `slots` omitted or empty.

### 2. `book_appointment`
**args**
```jsonc
{
  "patient": {
    "first_name": "John",        // string, required.
    "last_name": "Doe",          // string, required.
    "dob": "1985-03-22",         // "YYYY-MM-DD", required. Used to find-or-create the patient.
    "phone": "+447700900123"     // E.164, required. For the confirmation SMS.
  },
  "treatment_key": "exam",       // string, required.
  "practitioner_id": "dentally_practitioner_101",  // string, required. The chosen slot's practitioner.
  "start": "2026-06-10T14:00:00+01:00"             // ISO 8601, required. The chosen slot start.
}
```
**response** — `status` ∈ { `booked`, `slot_taken`, `error` }
```jsonc
{ "status": "booked", "appointment_id": "appt_555", "message": "You're booked in." }
```
- `slot_taken` = the slot was taken between offer and write → the agent apologises and calls
  `check_availability` again. **The agent must only confirm out loud on `booked`.**

### 3. `lookup_patient`
**args**
```jsonc
{ "first_name": "John", "last_name": "Doe", "dob": "1985-03-22" }  // all required
```
**response** — `status` ∈ { `found`, `not_found` }
```jsonc
{
  "status": "found",
  "patient_id": "pat_999",
  "upcoming": [
    { "appointment_id": "appt_555", "start": "2026-06-10T14:00:00+01:00", "treatment": "Examination", "practitioner_name": "Dr. Jane Smith" }
  ]
}
```
- Used before cancel/reschedule so the agent knows which appointment it's acting on.
- `not_found` = no patient matched; `patient_id`/`upcoming` omitted.

### 4. `cancel_appointment`
**args**
```jsonc
{ "appointment_id": "appt_555" }   // string, required. From a prior lookup_patient.
```
**response** — `status` ∈ { `cancelled`, `not_found`, `error` }
```jsonc
{ "status": "cancelled", "message": "That's cancelled for you." }
```

### 5. `reschedule_appointment`
Move an existing appointment to a new slot (the agent gets the new slot from `check_availability`
first). The backend performs the cancel + rebook atomically.

**args**
```jsonc
{
  "appointment_id": "appt_555",                    // string, required. The appointment being moved.
  "new_start": "2026-06-12T11:00:00+01:00",        // ISO 8601, required. The chosen new slot.
  "practitioner_id": "dentally_practitioner_101"   // string, optional. If moving to a different practitioner.
}
```
**response** — `status` ∈ { `rescheduled`, `slot_taken`, `not_found`, `error` }
```jsonc
{ "status": "rescheduled", "appointment_id": "appt_777", "message": "Moved to Friday at 11." }
```
- `appointment_id` in the response is the **new** appointment id.
- `slot_taken` = the new slot was taken first → re-offer. Agent only confirms on `rescheduled`.

---

## The full status table (the part that must not drift)

| function | allowed `status` values |
|----------|------------------------|
| `check_availability`     | `ok`, `no_slots` |
| `book_appointment`       | `booked`, `slot_taken`, `error` |
| `lookup_patient`         | `found`, `not_found` |
| `cancel_appointment`     | `cancelled`, `not_found`, `error` |
| `reschedule_appointment` | `rescheduled`, `slot_taken`, `not_found`, `error` |

---

## Open questions for B / the client

- **OPEN:** Confirm the `treatment_key` values the agent offers exactly match config keys — a typo
  here fails bookings silently. Reconcile against Contract 1 `treatment_types`.
- **OPEN:** Does the agent ever need a "list practitioners / treatments" call, or are those baked
  into the prompt from config? (Leaning: baked in. Confirm with B.)
- **OPEN:** How does escalation surface — a sixth function call, or purely an agent prompt behaviour
  with a transfer? (Leaning: prompt + transfer, no webhook. Confirm against config `escalation`.)
- **OPEN:** Should `check_availability` accept a "soonest" mode (no explicit dates) for "earliest
  you've got"? If yes, define how (e.g. `date_from` omitted = today).

## How we'll test this contract

1. **Shape test:** every example request/response in `contract-2-examples.json` is valid JSON, every
   request carries the full envelope, and every `status` is in the allowed set above. (Automated.)
2. **Cross-contract test:** the `slots` / `upcoming` / `appointment` shapes line up with what the PMS
   layer (Contract 3) returns — checked when Contract 3 is encoded.
3. **Live test:** once the webhook handler exists, B's Retell agent calls each function and the
   round-trip works end to end (first with dummy responses, then real).
