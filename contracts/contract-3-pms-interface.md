# Contract 3 — PMS Interface

**Status:** DRAFT v1 — 2026-06-06
**Owner:** Person A (defines the interface & writes every implementation behind it)

The set of backend functions that talk to a practice management system. The webhook handlers
(Contract 2) call these and don't know or care which PMS is behind them. Worked return shapes:
[`contract-3-examples.json`](./contract-3-examples.json).

The whole point: **one interface, swappable implementations.**

```
PMS interface (these functions)
   |
   +-- MockPMS    <- building now. Fake data, in-memory / Supabase. No external account.
   +-- Cliniko    <- later. Real, self-serve API key. Has its own availability endpoint.
   +-- Dentally   <- future, when the client gives us access.
```

---

## Design rules (read first)

1. **One implementation per tenant instance.** A PMS implementation is constructed for a single
   practice — it holds that practice's config + credentials. No tenant id is passed into the methods.
2. **Behaviour is the contract, not implementation.** Each method promises an output *shape* and
   *meaning*. How it gets there (compute slots vs. call an availability endpoint) is private to the
   implementation. The handlers must work unchanged across Mock, Cliniko, and Dentally.
3. **The booking path never lies.** `create_appointment` re-checks at write time and returns
   `slot_taken` on a race. A success result means the write actually happened. No optimistic confirms.
4. **Reschedule is not a PMS function.** The webhook reschedule handler composes
   `cancel_appointment` + `create_appointment`. Keeps the interface minimal.
5. **Return shapes match Contract 2's needs.** `Slot`, `Appointment`, `CreateResult` carry exactly
   the fields the webhook responses need, so handlers mostly pass shapes through.
6. **Times are ISO 8601 with offset**, in the practice's timezone.

---

## The functions

### `find_patient(first_name, last_name, dob)` → `Patient | null`
Look up a patient by name + date of birth. Returns the patient **with their upcoming appointments**
populated, or `null` if no match.

### `create_patient(first_name, last_name, dob, phone)` → `Patient`
Create a new patient record. Called when `find_patient` returned `null`. Returns the new patient
(with an empty `upcoming`).

### `get_available_slots(treatment_key, practitioner_id, date_from, date_to)` → `Slot[]`
Free slots for that treatment in the date range. `practitioner_id` may be `null` = any practitioner
who performs that treatment. Returns a small handful, ordered by `start`.
> **Where the slot logic lives.** MockPMS and Dentally **compute** free slots (working hours from
> config − booked appointments − breaks, sized to the treatment's duration). Cliniko asks its own
> availability endpoint. Same output shape either way, so the slot-calc code is shared internal
> logic reused by Mock + Dentally; Cliniko doesn't need it.

### `create_appointment(patient_id, treatment_key, practitioner_id, start)` → `CreateResult`
Book an appointment. **Re-checks the slot at write time.** Returns
`{ "status": "booked", "appointment": {...} }`, or `{ "status": "slot_taken" }` if the slot was
taken since it was offered. Never confirms a booking that didn't write.

### `cancel_appointment(appointment_id)` → `{ "status": "cancelled" | "not_found" }`
Cancel an appointment by id.

---

## The shapes everything returns

### `Patient`
```jsonc
{
  "id": "pat_999",                 // string. PMS patient id.
  "first_name": "John",
  "last_name": "Doe",
  "dob": "1985-03-22",             // "YYYY-MM-DD"
  "phone": "+447700900123",        // E.164
  "upcoming": [ /* Appointment objects, status "booked", start in the future */ ]
}
```

### `Appointment`
```jsonc
{
  "id": "appt_555",                // string. PMS appointment id.
  "start": "2026-06-10T14:00:00+01:00",   // ISO 8601 with offset
  "end": "2026-06-10T14:20:00+01:00",     // ISO 8601 with offset
  "treatment_key": "exam",         // config treatment key
  "treatment_name": "Examination", // spoken name
  "practitioner_id": "dentally_practitioner_101",
  "practitioner_name": "Dr. Jane Smith",
  "status": "booked"               // "booked" | "cancelled"
}
```

### `Slot`
```jsonc
{
  "start": "2026-06-10T14:00:00+01:00",   // ISO 8601 with offset
  "practitioner_id": "dentally_practitioner_101",
  "practitioner_name": "Dr. Jane Smith"
}
```

### `CreateResult`
```jsonc
{ "status": "booked", "appointment": { /* Appointment */ } }   // on success
{ "status": "slot_taken" }                                     // on race
```

**How these map to Contract 2:** a `Slot` → `check_availability.slots`; an `Appointment` →
`lookup_patient.upcoming` (id→`appointment_id`, `treatment_name`→`treatment`); `CreateResult.status`
→ `book_appointment.status`. So the handlers are thin reshapers.

---

## MockPMS — how the first implementation behaves

- Stores patients + appointments in memory (or a Supabase table) per tenant.
- `get_available_slots` runs the **real** slot-calc against the config's working hours — so the
  hardest, most error-prone piece is built and tested for real, just with made-up bookings.
- We can force any case on demand for testing: no slots, a `slot_taken` race, an existing patient.
- When Cliniko/Dentally arrives, we write that implementation behind this same interface and the
  handlers, slot logic, calls, and dashboard don't change.

## Future: Dentally implementation notes (when access comes)

- **No availability endpoint** → Dentally's `get_available_slots` reuses the shared slot-calc.
- `create_appointment` needs a room id + payment-plan id + a `reason` value (all from config).
- Stamp a call/session reference into the appointment `metadata` field for traceability.
- Per-practice **cancellation reasons** must be fetched + cached at onboarding and mapped on cancel.
- None of this leaks through the interface — it's all internal to the Dentally implementation.

---

## Open questions

- **OPEN:** Does `find_patient` need to handle duplicates (two patients, same name + DOB)? Decide
  the rule (e.g. return the most recent, or flag ambiguous) before the real PMS, where it can happen.
- **OPEN:** Where does MockPMS state live — pure in-memory (resets each run) or a Supabase table
  (persists, closer to real)? Leaning in-memory for the first build, Supabase when wiring the dashboard.
- **OPEN:** Slot granularity + how many slots to return — fixed 15-min grid, return first ~6? Confirm
  once we see how the agent offers them in real calls.

## How we'll test this contract

1. **Shape test:** the example return objects in `contract-3-examples.json` are valid JSON and carry
   exactly the fields Contract 2's responses need. (Automated — already passing.)
2. **Behaviour test:** the MockPMS implementation is exercised by a test script —
   find/create patient, compute slots (respecting hours, breaks, and existing bookings), book,
   hit a `slot_taken` race, cancel, and confirm a cancelled slot frees up again.
3. **Swap test (later):** when Cliniko/Dentally is written, the same handler tests pass against it
   unchanged — proving the interface held.
