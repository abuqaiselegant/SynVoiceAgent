# Generic Booking-Agent Contract

**Status:** DRAFT v1 — 2026-06-06
**Owner:** Person A (defines & implements) · Person B (configures the agent + fills config per client)

A domain-agnostic version of the three contracts. The booking machinery — hours, resources,
services, slots, bookings, customers — is identical across industries. Only the **vocabulary** and a
couple of **domain-specific fields** change. This contract captures the neutral core so the same
backend serves a **dental practice, a mechanic shop, or a restaurant** by configuration alone.

The dental contracts in `../contract-1/2/3` are simply the **dental instance** of this generic core.

Worked configs for three domains:
[`example-dental.json`](./example-dental.json) ·
[`example-restaurant.json`](./example-restaurant.json) ·
[`example-mechanic.json`](./example-mechanic.json).

---

## Vocabulary mapping

| Generic term            | Dental        | Mechanic            | Restaurant          |
|-------------------------|---------------|---------------------|---------------------|
| **business**            | practice      | garage              | restaurant          |
| **resource** (bookable) | practitioner  | bay / mechanic      | table               |
| **service**             | treatment     | repair (MOT, oil)   | sitting (lunch/dinner) |
| **booking**             | appointment   | job                 | reservation         |
| **customer**            | patient       | customer            | guest               |
| **booking system**      | Dentally      | shop software       | reservation system  |

---

## The two knobs that absorb every domain difference

Everything domain-specific rides in configuration, not code:

1. **`customer_identity`** — the list of fields used to recognise a returning customer.
   Dental `["last_name","dob"]` · Restaurant `["phone"]` · Mechanic `["last_name","phone"]`.

2. **`booking_fields`** — extra data the agent collects per booking, beyond the standard
   `first_name` / `last_name` / `phone`. Each declares a `key`, `label`, `type`, `required`. The
   collected values travel in a generic **`attributes`** map on the customer/booking.
   Dental `dob` · Restaurant `party_size` · Mechanic `vehicle_reg`.

Plus one structural field: **`capacity`** on a resource (a table seats N; a dentist/bay = 1).

The slot engine, webhook handlers, and booking-system interface are **identical** across all
domains. Swapping domain = swapping the config file (and the agent's spoken wording).

---

## Design rules

1. **Neutral nouns only in code.** Code says `resource`, `service`, `booking`, `customer`. Domain
   words ("patient", "table") appear only in config values and the agent's prompt.
2. **Domain data rides in `attributes`, never new columns.** Adding `party_size` or `vehicle_reg`
   for a new domain must not touch the schema — declare it in `booking_fields`, read it from
   `attributes`.
3. **Backend-specific settings live in `booking_system_config`** (opaque to the core; the chosen
   implementation interprets it — e.g. dental room/payment-plan ids).
4. **Forward-compatible** (as Contract 1): `schema_version` bumps only on breaking change; new
   fields additive + optional; consumers ignore unknown keys.
5. **Times** are 24h `"HH:MM"` in `business.timezone` (config) / ISO 8601 with offset (over the wire).

---

# Layer 1 — Config schema (generic)

```jsonc
{
  "schema_version": 1,
  "tenant_id": "uuid",
  "domain": "dental",            // label only: "dental" | "restaurant" | "mechanic" | ...
  "booking_system": "mock",      // which implementation: "mock" | "dentally" | "cliniko" | ...

  "business": {
    "name": "Bright Smiles Dental",
    "timezone": "Europe/London",
    "phone": "+441162345678",
    "address": "12 High St, Leicester",   // optional
    "location_notes": "Free parking on Mill Lane."  // optional
  },

  "opening_hours": { /* 7 day keys; null = closed; { open, close, breaks:[{start,end}] } */ },

  // The bookable units — a person (dentist, mechanic) OR a thing (table, bay).
  "resources": [
    {
      "id": "res_101",              // backend id
      "name": "Dr. Jane Smith",     // spoken
      "label": "Dentist",           // human type/role
      "service_keys": ["exam"],     // which services this resource delivers
      "capacity": 1,                // optional, default 1. Restaurant table = seats.
      "working_hours": { /* optional; same shape as opening_hours; else uses business hours */ }
    }
  ],

  // The bookable services — treatment / repair / sitting.
  "services": [
    {
      "key": "exam",                    // stable internal id, never spoken
      "name": "Examination",            // spoken
      "duration_minutes": 20,
      "booking_system_ref": "examination",  // backend's id/enum for this service
      "deposit": { "required": false, "amount_pence": 0 },   // optional
      "price": { "display": "£25.80", "notes": "NHS Band 1" }, // optional
      "attributes": { "funding": "nhs" }   // optional, free domain-specific extras
    }
  ],

  // KNOB 1 — how to identify a returning customer.
  "customer_identity": ["last_name", "dob"],

  // KNOB 2 — extra fields collected per booking (beyond first_name/last_name/phone).
  "booking_fields": [
    { "key": "dob", "label": "date of birth", "type": "date", "required": true }
  ],

  "booking_system_config": { /* optional, opaque. e.g. dental rooms + payment plans */ },

  "faq":        [ { "key": "parking", "question": "...", "answer": "..." } ],
  "escalation": { "transfer_number": "+44...", "always_escalate": ["emergency"], "take_message_when_unreachable": true },
  "sms": {
    "sender_name": "BrightSmile",
    "templates": {
      "booking_confirmation": "Hi {{customer_name}}, your {{service}} with {{resource}} is booked for {{date}} at {{time}}.",
      "cancellation": "Hi {{customer_name}}, your booking on {{date}} at {{time}} is cancelled.",
      "reschedule": "Hi {{customer_name}}, your booking is moved to {{date}} at {{time}}."
    }
  }
}
```

- **`booking_fields[].type`** ∈ `text` | `number` | `date` | `phone` | `email` | `select`.
- **`customer_identity`** values must each be a standard field (`first_name`/`last_name`/`phone`) or
  a declared `booking_fields[].key`.
- **SMS placeholders:** `{{customer_name}}`, `{{service}}`, `{{resource}}`, `{{date}}`, `{{time}}`.

---

# Layer 2 — Webhook (generic)

**Common request envelope** (every function):
```jsonc
{
  "call_id": "abc123",
  "to_number": "+441162345678",   // identifies the tenant
  "from_number": "+447700900123",
  "function": "check_availability",
  "args": { /* per function */ }
}
```
**Common response:** `{ "status": "...", "message": "...", /* data */ }`.

### Five intents

| function | args (key ones) | response data | `status` values |
|----------|-----------------|---------------|-----------------|
| `check_availability` | `service_key`, `resource_id`\|null, `date_from`, `date_to`, `attributes` | `slots[]` | `ok`, `no_slots` |
| `book` | `customer{first_name,last_name,phone}`, `service_key`, `resource_id`, `start`, `attributes` | `booking_id` | `booked`, `slot_taken`, `error` |
| `lookup_customer` | `identity{...customer_identity fields}` | `customer_id`, `upcoming[]` | `found`, `not_found` |
| `cancel` | `booking_id` | — | `cancelled`, `not_found`, `error` |
| `reschedule` | `booking_id`, `new_start`, `resource_id`? | `booking_id` (new) | `rescheduled`, `slot_taken`, `not_found`, `error` |

- **`attributes`** carries the declared `booking_fields` (e.g. `{"party_size": 4}`). It can affect
  availability — e.g. the backend only offers tables whose `capacity >= party_size`.
- The agent only confirms out loud on `booked` / `rescheduled`. On `error`, it falls back
  (take a message / transfer). `slot_taken` → re-offer via `check_availability`.

---

# Layer 3 — Booking-system interface (generic)

Five functions, one implementation per tenant (Mock now; Dentally/Cliniko/OpenTable later behind
the same interface).

| function | returns |
|----------|---------|
| `find_customer(identity)` | `Customer` \| null (with `upcoming` bookings) |
| `create_customer(first_name, last_name, phone, attributes)` | `Customer` |
| `get_available_slots(service_key, resource_id, date_from, date_to, attributes)` | `Slot[]` |
| `create_booking(customer_id, service_key, resource_id, start, attributes)` | `CreateResult` |
| `cancel_booking(booking_id)` | `{ status: "cancelled" \| "not_found" }` |

**Shapes**
```jsonc
// Slot
{ "start": "2026-06-10T14:00:00+01:00", "resource_id": "res_101", "resource_name": "Dr. Jane Smith" }

// Booking
{ "id": "bk_555", "start": "...", "end": "...", "service_key": "exam", "service_name": "Examination",
  "resource_id": "res_101", "resource_name": "Dr. Jane Smith", "status": "booked" }

// Customer
{ "id": "cust_999", "first_name": "John", "last_name": "Doe", "phone": "+447700900123",
  "attributes": { "dob": "1985-03-22" }, "upcoming": [ /* Booking */ ] }

// CreateResult
{ "status": "booked", "booking": { /* Booking */ } }   // or { "status": "slot_taken" }
```

- `get_available_slots` computes slots the same way for every domain: resource working hours
  (or business hours) − existing bookings − breaks, sized to the service duration, filtered by any
  relevant `attributes` (e.g. `capacity >= party_size`). Reschedule = cancel + create at the handler.

---

## Adding a new domain — the recipe

1. Write a config: set `domain`, list `resources` + `services`, set `customer_identity`, declare
   `booking_fields`, fill `faq`/`escalation`/`sms`.
2. Point `booking_system` at an implementation (start with `mock`).
3. Write the agent's prompt in that domain's language ("table for two", "book your MOT").
4. **No backend code changes.** The slot engine, handlers, and interface are already generic.

---

## Open questions

- **OPEN:** Do any domains need **multi-unit bookings** (e.g. join two tables, or a job that ties up
  two bays)? v1 assumes one resource per booking. If needed, model as `capacity` + party size only.
- **OPEN:** Recurring/series bookings (e.g. a course of treatment, weekly table) — out of scope for
  v1? Likely yes; note for later.
- **OPEN:** `select`-type `booking_fields` — do we need an `options` list on the field definition?
  Add when a domain first needs it.
- **OPEN:** Should `attributes` be validated against `booking_fields` at the webhook boundary, or
  trusted from the agent? Leaning: validate (required present, types right) before booking.

## How we'll test this contract

1. **One schema, three domains:** the dental, restaurant, and mechanic example configs all validate
   against a single generic checker (top-level keys, 7-day hours, resource→service references,
   `customer_identity` resolves to standard or declared fields, `booking_fields` types valid, SMS
   rules). Automated — see the test alongside these files.
2. **Behaviour (later):** the same MockPMS/handler tests pass when pointed at a dental config and a
   restaurant config — proving the core is domain-neutral.
