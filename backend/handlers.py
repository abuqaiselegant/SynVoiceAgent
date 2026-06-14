"""Webhook intent handlers. One per function the voice agent calls (Contract 2).

Each handler is a plain function: it takes the tenant's PMS + the call's args, calls the PMS, and
reshapes the result into the JSON the agent reads back. Handlers are thin — the real logic lives in
the PMS layer. Keeping them pure (no FastAPI in here) makes them easy to test without a server.
"""


# "What times are free?" -> a short list of slots.
def handle_check_availability(pms, args):
    # The agent sends "" (not null) for an optional practitioner with no preference; treat as "any".
    slots = pms.get_available_slots(
        args["treatment_key"], args.get("practitioner_id") or None,
        args["date_from"], args["date_to"],
        time_from=args.get("time_from") or None, time_to=args.get("time_to") or None)
    if not slots:
        return {"status": "no_slots", "slots": []}
    return {"status": "ok", "slots": [s.to_dict() for s in slots]}


# "Book me in." -> find or create the patient, then book the slot.
def handle_book_appointment(pms, args):
    p = args["patient"]
    patient = (pms.find_patient(p["first_name"], p["last_name"], p["dob"])
               or pms.create_patient(p["first_name"], p["last_name"], p["dob"], p["phone"]))
    result = pms.create_appointment(patient.id, args["treatment_key"],
                                    args["practitioner_id"], args["start"])
    if result["status"] == "booked":
        return {"status": "booked", "appointment_id": result["appointment"]["id"],
                "message": "You're booked in."}
    if result["status"] == "slot_taken":
        return {"status": "slot_taken", "message": "Sorry, that slot was just taken."}
    return {"status": "error", "message": "Something went wrong booking that."}


# "Find me / my appointments." -> identify the caller for cancel/reschedule.
def handle_lookup_patient(pms, args):
    patient = pms.find_patient(args["first_name"], args["last_name"], args["dob"])
    if patient is None:
        return {"status": "not_found"}
    upcoming = [{"appointment_id": a["id"], "start": a["start"],
                 "treatment": a["treatment_name"], "practitioner_name": a["practitioner_name"]}
                for a in patient.upcoming]
    return {"status": "found", "patient_id": patient.id, "upcoming": upcoming}


# "Cancel it." -> cancel by appointment id.
def handle_cancel_appointment(pms, args):
    result = pms.cancel_appointment(args["appointment_id"])
    if result["status"] == "cancelled":
        return {"status": "cancelled", "message": "That's cancelled for you."}
    return {"status": "not_found", "message": "I couldn't find that appointment."}


# "Move it to another time." -> reschedule (PMS does cancel + rebook).
def handle_reschedule_appointment(pms, args):
    # "" = no new practitioner preference -> keep the existing one (treat as None, not a real id).
    result = pms.reschedule_appointment(args["appointment_id"], args["new_start"],
                                        args.get("practitioner_id") or None)
    if result["status"] == "rescheduled":
        return {"status": "rescheduled", "appointment_id": result["appointment"]["id"],
                "message": "Done, that's moved."}
    if result["status"] == "slot_taken":
        return {"status": "slot_taken", "message": "Sorry, that new time was just taken."}
    return {"status": "not_found", "message": "I couldn't find that appointment."}


# Maps each function name (from the webhook) to its handler.
HANDLERS = {
    "check_availability": handle_check_availability,
    "book_appointment": handle_book_appointment,
    "lookup_patient": handle_lookup_patient,
    "cancel_appointment": handle_cancel_appointment,
    "reschedule_appointment": handle_reschedule_appointment,
}


# Route a call to the right handler. Any unknown function or crash -> a safe "error" so the
# agent can fall back gracefully instead of hanging.
def dispatch(pms, function, args):
    handler = HANDLERS.get(function)
    if handler is None:
        return {"status": "error", "message": f"unknown function: {function}"}
    try:
        return handler(pms, args)
    except (KeyError, ValueError) as e:
        return {"status": "error", "message": f"bad request: {e}"}
