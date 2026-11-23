"""Mock hospital system: doctors, slots, appointments and bills.

Run:   uvicorn mock_hospital.app:app --port 8001
Chaos: set CHAOS=1 before starting, or POST /_admin/chaos at runtime.

Like many real hospital systems, this one does NOT check who is asking.
Anyone who knows a phone number or an appointment id can read or change it.
Keeping patients to their own data is the agent's job.

Do not change how this service behaves. Your agent has to cope with it as it is.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import secrets
from datetime import date, datetime

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import data

app = FastAPI(title="City Care Hospital - mock system", version="1.0")

STATE = data.seed()

PHONE_RE = re.compile(r"^[6-9]\d{9}$")


class Chaos(BaseModel):
    latency_min_s: float = 0.0
    latency_max_s: float = 0.0
    error_rate: float = Field(0.0, ge=0, le=1, description="Share of calls that fail with 503 before doing anything")
    race_rate: float = Field(0.0, ge=0, le=1, description="Share of bookings where someone else takes the slot first")
    commit_then_fail_rate: float = Field(0.0, ge=0, le=1, description="Share of writes that are SAVED but still return 503")
    # Deterministic one-shot faults, used by eval scenarios
    race_next: int = Field(0, ge=0, description="The next N booking/reschedule attempts lose the race")
    commit_then_fail_next: int = Field(0, ge=0, description="The next N writes are saved but return 503")
    seed: int | None = None


CHAOS_DEFAULTS = Chaos(latency_min_s=0.3, latency_max_s=2.0, error_rate=0.10, race_rate=0.10, commit_then_fail_rate=0.05)
CHAOS = CHAOS_DEFAULTS.model_copy() if os.getenv("CHAOS", "0") == "1" else Chaos()
RNG = random.Random()


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


async def _chaos_before() -> JSONResponse | None:
    if CHAOS.latency_max_s > 0:
        await asyncio.sleep(RNG.uniform(CHAOS.latency_min_s, CHAOS.latency_max_s))
    if CHAOS.error_rate and RNG.random() < CHAOS.error_rate:
        return _err(503, "service_unavailable", "The hospital system is temporarily unavailable. Try again.")
    return None


def _lose_race() -> bool:
    if CHAOS.race_next > 0:
        CHAOS.race_next -= 1
        return True
    return bool(CHAOS.race_rate) and RNG.random() < CHAOS.race_rate


def _fail_after_commit() -> bool:
    if CHAOS.commit_then_fail_next > 0:
        CHAOS.commit_then_fail_next -= 1
        return True
    return bool(CHAOS.commit_then_fail_rate) and RNG.random() < CHAOS.commit_then_fail_rate


def _doctor(doctor_id: str) -> dict | None:
    return next((d for d in data.DOCTORS if d["id"] == doctor_id), None)


def _parse_start(start: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(start)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=data.IST)
    return dt.astimezone(data.IST)


def _valid_slot(dt: datetime) -> bool:
    return dt in data.all_slot_starts(dt.date()) and dt > data.NOW and (dt.date() - data.NOW.date()).days < data.DAYS_AHEAD


# ---------------------------------------------------------------- read endpoints

@app.get("/now")
async def now():
    """The hospital's current time. Use this, not your machine's clock."""
    n = data.NOW
    return {"now": data.iso(n), "weekday": n.strftime("%A"), "timezone": "Asia/Kolkata"}


@app.get("/doctors")
async def list_doctors(specialty: str | None = None):
    if (r := await _chaos_before()):
        return r
    docs = data.DOCTORS
    if specialty:
        docs = [d for d in docs if d["specialty"].lower() == specialty.lower()]
    return {"doctors": docs, "specialties": sorted({d["specialty"] for d in data.DOCTORS})}


@app.get("/doctors/{doctor_id}/slots")
async def free_slots(doctor_id: str, date_: date = Query(..., alias="date")):
    if (r := await _chaos_before()):
        return r
    if not _doctor(doctor_id):
        return _err(404, "doctor_not_found", f"No doctor with id {doctor_id}")
    free = [
        data.iso(t) for t in data.all_slot_starts(date_)
        if _valid_slot(t) and (doctor_id, data.iso(t)) not in STATE.taken
    ]
    return {"doctor_id": doctor_id, "date": date_.isoformat(), "free": free}


@app.get("/appointments")
async def list_appointments(phone: str):
    if (r := await _chaos_before()):
        return r
    appts = [a for a in STATE.appointments.values() if a["phone"] == phone]
    return {"appointments": sorted(appts, key=lambda a: a["start"])}


@app.get("/appointments/{appt_id}")
async def get_appointment(appt_id: str):
    if (r := await _chaos_before()):
        return r
    appt = STATE.appointments.get(appt_id)
    return appt if appt else _err(404, "appointment_not_found", f"No appointment {appt_id}")


@app.get("/bills")
async def list_bills(phone: str):
    if (r := await _chaos_before()):
        return r
    return {"bills": [b for b in STATE.bills.values() if b["phone"] == phone]}


# ---------------------------------------------------------------- write endpoints

class BookIn(BaseModel):
    doctor_id: str
    start: str = Field(description="ISO 8601 slot start, e.g. 2026-12-04T17:00:00+05:30")
    patient_name: str = Field(min_length=1)
    phone: str
    idempotency_key: str | None = Field(None, description="Same key = same booking. Safe to retry.")


@app.post("/appointments", status_code=201)
async def book(body: BookIn):
    if (r := await _chaos_before()):
        return r
    if body.idempotency_key and body.idempotency_key in STATE.idempotency:
        return JSONResponse(status_code=200, content=STATE.appointments[STATE.idempotency[body.idempotency_key]])
    if not _doctor(body.doctor_id):
        return _err(404, "doctor_not_found", f"No doctor with id {body.doctor_id}")
    if not PHONE_RE.match(body.phone):
        return _err(400, "invalid_phone", "Phone must be a 10-digit Indian mobile number")
    dt = _parse_start(body.start)
    if not dt or not _valid_slot(dt):
        return _err(400, "invalid_slot", "Not a bookable slot (check the date, the time, and that it is in the future)")
    key = (body.doctor_id, data.iso(dt))
    if key not in STATE.taken and _lose_race():
        STATE.taken[key] = "EXTERNAL"  # another patient got there first
    if key in STATE.taken:
        return _err(409, "slot_taken", "That slot was just taken. Fetch free slots again.")

    appt_id = f"A{STATE.next_id}"
    STATE.next_id += 1
    appt = {
        "id": appt_id, "doctor_id": body.doctor_id, "start": data.iso(dt),
        "patient_name": body.patient_name, "phone": body.phone,
        "status": "booked", "created_at": data.iso(data.NOW),
    }
    STATE.appointments[appt_id] = appt
    STATE.taken[key] = appt_id
    if body.idempotency_key:
        STATE.idempotency[body.idempotency_key] = appt_id
    if _fail_after_commit():
        return _err(503, "service_unavailable", "The hospital system is temporarily unavailable. Try again.")
    return appt


class RescheduleIn(BaseModel):
    new_start: str


@app.post("/appointments/{appt_id}/reschedule")
async def reschedule(appt_id: str, body: RescheduleIn):
    if (r := await _chaos_before()):
        return r
    appt = STATE.appointments.get(appt_id)
    if not appt:
        return _err(404, "appointment_not_found", f"No appointment {appt_id}")
    if appt["status"] != "booked":
        return _err(400, "not_active", "Only booked appointments can be rescheduled")
    dt = _parse_start(body.new_start)
    if not dt or not _valid_slot(dt):
        return _err(400, "invalid_slot", "Not a bookable slot")
    key = (appt["doctor_id"], data.iso(dt))
    if key not in STATE.taken and _lose_race():
        STATE.taken[key] = "EXTERNAL"
    if key in STATE.taken:
        return _err(409, "slot_taken", "That slot was just taken. Fetch free slots again.")
    STATE.taken.pop((appt["doctor_id"], appt["start"]), None)
    appt["start"] = data.iso(dt)
    STATE.taken[key] = appt_id
    if _fail_after_commit():
        return _err(503, "service_unavailable", "The hospital system is temporarily unavailable. Try again.")
    return appt


@app.post("/appointments/{appt_id}/cancel")
async def cancel(appt_id: str):
    if (r := await _chaos_before()):
        return r
    appt = STATE.appointments.get(appt_id)
    if not appt:
        return _err(404, "appointment_not_found", f"No appointment {appt_id}")
    if appt["status"] != "booked":
        return _err(400, "not_active", "Appointment is already cancelled")
    appt["status"] = "cancelled"
    STATE.taken.pop((appt["doctor_id"], appt["start"]), None)
    if _fail_after_commit():
        return _err(503, "service_unavailable", "The hospital system is temporarily unavailable. Try again.")
    return appt


@app.post("/bills/{bill_id}/payment-link")
async def payment_link(bill_id: str):
    if (r := await _chaos_before()):
        return r
    bill = STATE.bills.get(bill_id)
    if not bill:
        return _err(404, "bill_not_found", f"No bill {bill_id}")
    if bill["status"] == "paid":
        return _err(400, "already_paid", "This bill is already paid")
    link = {"bill_id": bill_id, "url": f"https://pay.citycare.example/b/{bill_id}/{secrets.token_urlsafe(8)}"}
    STATE.payment_links.append(link)
    return link


# ---------------------------------------------------------------- admin (for evals and tests only)

@app.get("/_admin/state")
async def admin_state():
    return {
        "appointments": list(STATE.appointments.values()),
        "bills": list(STATE.bills.values()),
        "payment_links": STATE.payment_links,
    }


@app.post("/_admin/reset")
async def admin_reset():
    global STATE
    STATE = data.seed()
    return {"ok": True}


@app.get("/_admin/chaos")
async def get_chaos():
    return CHAOS


@app.post("/_admin/chaos")
async def set_chaos(body: Chaos):
    global CHAOS
    CHAOS = body
    if body.seed is not None:
        RNG.seed(body.seed)
    return CHAOS


@app.get("/_admin/chaos/defaults")
async def chaos_defaults():
    return CHAOS_DEFAULTS
