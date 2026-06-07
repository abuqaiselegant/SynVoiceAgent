# Contract 1 — Config Schema

**Status:** DRAFT v1 — 2026-06-05
**Owner:** Person A (defines & reads it) · Person B (fills & edits it via the dashboard)

This is the per-tenant settings document. One config blob per client (practice). Person B fills
it from the client questionnaire and edits it through the dashboard; Person A's booking logic,
slot engine, and out-of-hours check all read it.

---

## Design rules (read first)

1. **One config = one tenant.** Every config belongs to exactly one `tenant_id`. No shared config.
2. **Forward-compatible.** Adding a field later must not break existing clients. Therefore:
   - `schema_version` is bumped only on a **breaking** change.
   - All *new* fields are **additive and optional**, with a safe default when absent.
   - Consumers (backend + dashboard) **ignore unknown keys** rather than erroring.
3. **PMS-specific IDs are opaque strings.** `pms_reason`, `room` ids, `payment_plan` ids etc. are
   whatever the active PMS uses. The PMS layer (Contract 3) interprets them. Config just stores them.
4. **Audit data is NOT in this blob.** `created_at`, `updated_at`, `updated_by` live as columns on
   the Supabase row, not inside the JSON. Keeps the config clean and diffable.
5. **`*_minutes` and times.** Durations are integer minutes. Times are 24h `"HH:MM"` strings in the
   practice's `timezone`. No timezone offsets inside time strings.

---

## Top-level shape

```jsonc
{
  "schema_version": 1,            // int, required. Bumped only on breaking change.
  "tenant_id": "uuid",           // string, required. The client this config belongs to.
  "pms": "dentally",             // "mock" | "dentally" | "cliniko". Which PMS implementation to use.

  "practice":        { ... },     // identity + contact + location (FAQ uses location)
  "opening_hours":   { ... },     // practice-level hours -> drives out-of-hours behaviour
  "practitioners":   [ ... ],     // who can be booked, and their per-person hours
  "treatment_types": [ ... ],     // bookable treatments, durations, PMS reason mapping
  "rooms":           [ ... ],     // PMS room ids (Dentally). Cliniko may leave empty.
  "payment_plans":   [ ... ],     // PMS payment-plan ids (Dentally). Cliniko may leave empty.
  "faq":             [ ... ],     // static Q&A the agent answers
  "escalation":      { ... },     // when & where to hand off to a human
  "sms":             { ... },     // sender name + message templates
  "retention":       { ... }      // optional. how long we keep call data before auto-delete
}
```

---

## Field reference

### `practice` (required)
```jsonc
{
  "name": "Bright Smiles Dental",     // string, required. Spoken by the agent.
  "timezone": "Europe/London",        // IANA tz, required. All times in config are in this tz.
  "phone": "+441162345678",           // E.164, required. The practice's own main line.
  "address": "12 High St, Leicester, LE1 4AB",  // string, optional. Used by FAQ answers.
  "location_notes": "Free parking on Mill Lane, 2 min walk."  // string, optional. FAQ/directions.
}
```

### `opening_hours` (required)
Practice-level. Drives the **out-of-hours** greeting and the "is the practice open right now"
check (Person A owns that check). A `null` day = closed all day.
```jsonc
{
  "monday":    { "open": "09:00", "close": "17:30", "breaks": [ { "start": "13:00", "end": "14:00" } ] },
  "tuesday":   { "open": "09:00", "close": "17:30", "breaks": [] },
  "wednesday": { "open": "09:00", "close": "17:30", "breaks": [ { "start": "13:00", "end": "14:00" } ] },
  "thursday":  { "open": "09:00", "close": "19:00", "breaks": [] },
  "friday":    { "open": "09:00", "close": "16:00", "breaks": [] },
  "saturday":  { "open": "09:00", "close": "13:00", "breaks": [] },
  "sunday":    null
}
```
- `breaks` is an array (0..n) so a practice can have more than just lunch. Empty array = no breaks.
- All seven day keys must be present. Use `null` for closed days.

### `practitioners` (required, 1..n)
```jsonc
{
  "id": "a1b2c3",                 // string, required. The PMS practitioner id (Dentally id).
  "name": "Dr. Jane Smith",       // string, required. Spoken by the agent.
  "role": "Dentist",              // string, required. Free text: "Dentist", "Hygienist", etc.
  "treatment_keys": ["exam", "scale_polish"],  // which treatment_types.key this person performs
  "working_hours": {              // optional. Per-person hours for the SLOT ENGINE.
                                  //   If omitted, defaults to practice opening_hours.
                                  //   Same shape as opening_hours (7 day keys, null = day off).
    "monday":    { "open": "09:00", "close": "17:00", "breaks": [ { "start": "13:00", "end": "14:00" } ] },
    "tuesday":   null,
    "wednesday": { "open": "09:00", "close": "17:00", "breaks": [] },
    "thursday":  null,
    "friday":    { "open": "09:00", "close": "16:00", "breaks": [] },
    "saturday":  null,
    "sunday":    null
  }
}
```
- **Why both levels:** `opening_hours` answers "is the practice open?"; `working_hours` answers
  "when can THIS dentist be booked?" The slot engine subtracts booked time + breaks from
  `working_hours` (falling back to `opening_hours` if a practitioner has none).

### `treatment_types` (required, 1..n)
```jsonc
{
  "key": "scale_polish",          // string, required. Stable internal id. Never spoken. Used to
                                  //   link practitioners -> treatments and to map PMS reasons.
  "name": "Scale & Polish",       // string, required. The spoken/displayed name.
  "duration_minutes": 30,         // int, required. Drives slot sizing.
  "funding": "both",              // "nhs" | "private" | "both". Required.
  "pms_reason": "scale_and_polish",  // string, required. The PMS appointment `reason` enum value.
  "deposit": {                    // optional. Omit or null = no deposit.
    "required": true,
    "amount_pence": 2000          // int. 2000 = £20.00.
  },
  "price": {                      // optional. For FAQ / spoken pricing.
    "display": "£73.50",
    "notes": "NHS Band 1"
  }
}
```

### `rooms` (optional, may be empty)
PMS room ids the appointment-create call needs (Dentally). Cliniko may leave this empty.
```jsonc
[ { "id": "room_01", "name": "Surgery 1" }, { "id": "room_02", "name": "Surgery 2" } ]
```

### `payment_plans` (optional, may be empty)
PMS payment-plan ids (Dentally). Cliniko may leave this empty.
```jsonc
[ { "id": "pp_nhs", "name": "NHS" }, { "id": "pp_private", "name": "Private" } ]
```

### `faq` (required, may be empty)
Static answers the agent reads. Order is the priority order.
```jsonc
[
  { "key": "parking",  "question": "Is there parking?",        "answer": "Free parking on Mill Lane, a 2 minute walk." },
  { "key": "opening",  "question": "What are your hours?",     "answer": "We're open Monday to Friday 9 to 5:30, and Saturday mornings." }
]
```
- `key` is a stable handle (so the agent prompt can reference a specific answer); `question` is
  human-facing in the editor; `answer` is what the agent says.

### `escalation` (required)
```jsonc
{
  "transfer_number": "+441162345679",     // E.164, required. Where "get me a human" calls go.
  "always_escalate": ["emergency", "safeguarding", "complaint"],  // intents that ALWAYS hand off
  "take_message_when_unreachable": true   // bool. If transfer fails, take a message instead.
}
```
- `always_escalate` values are stable tags the agent/router recognise. Final list agreed with B
  against the webhook contract (Contract 2).

### `sms` (required)
```jsonc
{
  "sender_name": "Bright Smiles",   // string, required. Max 11 alphanumeric chars (Twilio sender id rule).
  "templates": {
    "booking_confirmation": "Hi {{patient_name}}, your {{treatment}} with {{practitioner}} is booked for {{date}} at {{time}}. Bright Smiles Dental.",
    "cancellation":         "Hi {{patient_name}}, your appointment on {{date}} at {{time}} has been cancelled. Call us to rebook.",
    "reschedule":           "Hi {{patient_name}}, your appointment is moved to {{date}} at {{time}}. Bright Smiles Dental."
  }
}
```
- Placeholders use `{{snake_case}}`. Available: `patient_name`, `treatment`, `practitioner`,
  `date`, `time`, `practice_name`. Unknown placeholders render literally (and are a config bug).

### `retention` (optional — compliance)
How many days we keep each kind of call data before it is **auto-deleted**. Driven by GDPR
data-minimisation (see `COMPLIANCE.md` §3.2). Omitted = system defaults. Numbers are agreed with
the practice. A scheduled delete job (built later) removes anything older than these — which
satisfies both the Retention Policy and the right-to-erasure requirement.
```jsonc
{
  "recordings_days": 30,     // int. delete call audio recordings after N days
  "transcripts_days": 90,    // int. delete call transcripts after N days
  "call_logs_days": 365      // int. delete call metadata / logs after N days
}
```
- We store **only references** to the patient (tenant id + PMS patient id), never a second copy of
  the patient record — so retention here covers call data, not patient records (those live in the PMS).

---

## Complete worked example

A full, valid config for a fictional Leicester practice lives at
[`contract-1-example.json`](./contract-1-example.json). Person B can use it as the template to fill
from the real questionnaire.

---

## Open questions for B / the client

- **OPEN:** Confirm the exact `always_escalate` tag list with B once Contract 2 (webhook) intents
  are named — they must line up.
- **OPEN:** Do any treatments need a Stripe deposit on booking? If yes, which, and how much?
  (Feeds `treatment_types[].deposit`; ties to the Phase 4 / Stripe decision.)
- **OPEN:** Are practitioner working hours actually different from practice hours for this client?
  If they're identical, we can omit per-practitioner `working_hours` entirely for v1.
- **OPEN:** SMS `sender_name` — is an alphanumeric sender id allowed for UK, or must it be a number?
  (Twilio/regulatory; affects whether `sender_name` is a name or a phone number.)

## How we'll test this contract

A config schema is "tested" two ways before we trust it:
1. **Parse test:** the example JSON validates against the shape (we encode it as a Pydantic model /
   JSON Schema in the *next* step and assert the example loads clean).
2. **Coverage test:** Person B tries to map the real client questionnaire onto it and reports any
   field with nowhere to go. Any gap = a schema change *we* (Person A) decide.
