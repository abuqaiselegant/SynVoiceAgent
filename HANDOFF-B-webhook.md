===============================================================================
 WEBHOOK HANDOFF  —  for Person B (Retell agent)
 From: Person A (backend)        Date: 2026-06-07
===============================================================================

The backend webhook is built and running. This file is everything you need to
wire the Retell agent to it. You don't need to read the code — just use the five
function names + parameters below, exactly as written.


-------------------------------------------------------------------------------
 1. THE WEBHOOK URL
-------------------------------------------------------------------------------

Right now it runs on A's machine:   http://127.0.0.1:8080/webhook

IMPORTANT: that's a LOCAL address — Retell's cloud can't reach it yet.
To connect Retell you need a PUBLIC https URL. Two options (ask A):
  (a) A deploys the backend (Railway/Render) -> you get a permanent https URL, or
  (b) A runs a tunnel (ngrok) -> you get a temporary https URL for testing.

Use whichever URL A gives you wherever this doc says <WEBHOOK_URL>.
You CAN still see how it behaves today using the curl examples in section 5.


-------------------------------------------------------------------------------
 2. HOW IT WORKS (one minute)
-------------------------------------------------------------------------------

- Your Retell agent calls one of FIVE functions during a call.
- Each call hits <WEBHOOK_URL> (a POST).
- The backend replies with JSON. Every reply has a "status" field.
- YOUR JOB: read "status" and decide what the agent says next.
- Only say "you're booked" / "it's moved" when status is "booked" / "rescheduled".

A handles all the Retell-payload plumbing (call id, the dialled number, etc.).
You just define the 5 functions with the names + parameters below and point them
at <WEBHOOK_URL>.


-------------------------------------------------------------------------------
 3. THE FIVE FUNCTIONS  (use these names EXACTLY)
-------------------------------------------------------------------------------

............................................................................
 (1) check_availability   — "what times are free?"
............................................................................
 Parameters:
   treatment_key    string   required   one of the keys in section 4
   practitioner_id  string   optional   null = any practitioner who does it
   date_from        string   required   "YYYY-MM-DD"
   date_to          string   required   "YYYY-MM-DD"

 Replies:
   { "status": "ok", "slots": [ { "start": "...", "practitioner_id": "...",
                                  "practitioner_name": "..." }, ... ] }
   { "status": "no_slots", "slots": [] }

 Agent: offer 2-3 of the returned slots. If no_slots, suggest other dates.


............................................................................
 (2) book_appointment     — "book me in"
............................................................................
 Parameters:
   patient          object   required   { first_name, last_name,
                                          dob ("YYYY-MM-DD"), phone }
   treatment_key    string   required
   practitioner_id  string   required   (from the slot the caller picked)
   start            string   required   (the slot's "start" value)

 Replies:
   { "status": "booked", "appointment_id": "...", "message": "..." }
   { "status": "slot_taken", "message": "..." }      <- someone took it first
   { "status": "error", "message": "..." }

 Agent: confirm out loud ONLY on "booked". On "slot_taken", apologise and call
        check_availability again to offer another time.


............................................................................
 (3) lookup_patient       — "find me / my appointments" (for cancel/reschedule)
............................................................................
 Parameters:
   first_name   string   required
   last_name    string   required
   dob          string   required   "YYYY-MM-DD"

 Replies:
   { "status": "found", "patient_id": "...",
     "upcoming": [ { "appointment_id": "...", "start": "...",
                     "treatment": "...", "practitioner_name": "..." }, ... ] }
   { "status": "not_found" }

 Agent: use this first when someone wants to cancel or move an appointment, so
        you know which appointment_id to act on.


............................................................................
 (4) cancel_appointment   — "cancel it"
............................................................................
 Parameters:
   appointment_id   string   required   (from lookup_patient)

 Replies:
   { "status": "cancelled", "message": "..." }
   { "status": "not_found", "message": "..." }


............................................................................
 (5) reschedule_appointment  — "move it to another time"
............................................................................
 Parameters:
   appointment_id   string   required
   new_start        string   required   (a "start" from check_availability)
   practitioner_id  string   optional   (only if moving to a different person)

 Replies:
   { "status": "rescheduled", "appointment_id": "...", "message": "..." } <- NEW id
   { "status": "slot_taken", "message": "..." }   <- new time taken; old one kept
   { "status": "not_found", "message": "..." }

 Agent: get the new time from check_availability first, then call this.
        Confirm out loud ONLY on "rescheduled".


-------------------------------------------------------------------------------
 4. VALID VALUES (for the dental test practice)
-------------------------------------------------------------------------------

 These come from the practice config. They WILL differ per practice — confirm the
 live list with A before go-live. For the current test practice:

 treatment_key   ->  spoken name
   exam          ->  "Examination"
   scale_polish  ->  "Scale & Polish"
   filling       ->  "Filling"
   emergency     ->  "Emergency Appointment"

 practitioner_id          ->  name (role)
   dentally_practitioner_101  ->  Dr. Jane Smith (Dentist)
   dentally_practitioner_102  ->  Aisha Khan (Hygienist)

 In your prompt, map what the caller SAYS ("a check-up", "a clean") to the right
 treatment_key. Getting this wrong fails the booking — check the mapping with A.


-------------------------------------------------------------------------------
 5. TRY IT NOW (without Retell — just to see the replies)
-------------------------------------------------------------------------------

 If you're on A's machine while the server is running, paste these in a terminal.
 (to_number "+441162345678" tells the backend which practice this is.)

 # what's free?
 curl -s -X POST http://127.0.0.1:8080/webhook -H 'Content-Type: application/json' \
   -d '{"to_number":"+441162345678","function":"check_availability",
        "args":{"treatment_key":"exam","practitioner_id":null,
                "date_from":"2026-06-10","date_to":"2026-06-12"}}'

 # book the 9am slot
 curl -s -X POST http://127.0.0.1:8080/webhook -H 'Content-Type: application/json' \
   -d '{"to_number":"+441162345678","function":"book_appointment",
        "args":{"patient":{"first_name":"John","last_name":"Doe",
                "dob":"1985-03-22","phone":"+447700900123"},
                "treatment_key":"exam","practitioner_id":"dentally_practitioner_101",
                "start":"2026-06-10T09:00:00+01:00"}}'

 Tip: the running server also has a click-to-try page at
      http://127.0.0.1:8080/docs   (open in a browser).

 Note: test data is in-memory and uses the real clock — use FUTURE dates, and
 anything you book is wiped when the server restarts.


-------------------------------------------------------------------------------
 6. YOUR STEPS  (what to do with this)
-------------------------------------------------------------------------------

 [ ] 1. Get the public <WEBHOOK_URL> from A (deployed URL, or an ngrok URL).
 [ ] 2. In Retell, open/create your agent.
 [ ] 3. Add the 5 functions above — EXACT names + parameters — all pointing at
        <WEBHOOK_URL>.
 [ ] 4. Write the prompts so the agent:
            - collects the right info (name, dob, treatment, dates),
            - maps spoken treatment names -> treatment_key (section 4),
            - calls the right function at the right moment.
 [ ] 5. Branch on "status" in every reply:
            booked / rescheduled  -> confirm out loud
            slot_taken            -> apologise, re-offer via check_availability
            no_slots              -> suggest other dates
            not_found             -> "I can't find that booking"
            error                 -> apologise / offer to take a message / transfer
 [ ] 6. Make a test call. Try to break it (mumble, wrong dates, cancel a
        non-existent booking).
 [ ] 7. Log what breaks; tag each as "prompt (mine)" or "backend (A's)".
        Review the list with A weekly.

 Anything the backend should return but doesn't? Tell A — don't work around it.

===============================================================================
 Full detail (if you want it): contracts/contract-2-webhook.md
===============================================================================
