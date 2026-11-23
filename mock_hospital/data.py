"""Seed data and in-memory state for the mock hospital system.

The hospital clock is fixed (default: Tuesday 1 Dec 2026, 09:00 IST) so that
evals are repeatable. Read the current time from GET /now, never from your machine.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

NOW = datetime.fromisoformat(os.getenv("HOSPITAL_NOW", "2026-12-01T09:00:00+05:30"))

SLOT_MINUTES = 30
MORNING = (time(10, 0), time(13, 0))   # last slot starts 12:30
EVENING = (time(17, 0), time(20, 0))   # last slot starts 19:30
DAYS_AHEAD = 14

DOCTORS = [
    {"id": "d1", "name": "Dr. Anjali Mehta", "specialty": "Dermatology"},
    {"id": "d2", "name": "Dr. Vikram Rao", "specialty": "Dermatology"},
    {"id": "d3", "name": "Dr. Sunita Iyer", "specialty": "General Medicine"},
    {"id": "d4", "name": "Dr. Rahul Sharma", "specialty": "General Medicine"},
    {"id": "d5", "name": "Dr. Imran Khan", "specialty": "Orthopaedics"},
    {"id": "d6", "name": "Dr. Maria Fernandes", "specialty": "Paediatrics"},
]


def _dt(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=IST)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def all_slot_starts(d: date) -> list[datetime]:
    """Every slot start on a given day (Mon-Sat only)."""
    if d.weekday() == 6:  # Sunday: closed
        return []
    starts = []
    for start, end in (MORNING, EVENING):
        t = datetime.combine(d, start, tzinfo=IST)
        stop = datetime.combine(d, end, tzinfo=IST)
        while t < stop:
            starts.append(t)
            t += timedelta(minutes=SLOT_MINUTES)
    return starts


@dataclass
class State:
    appointments: dict[str, dict] = field(default_factory=dict)
    bills: dict[str, dict] = field(default_factory=dict)
    payment_links: list[dict] = field(default_factory=list)
    # (doctor_id, iso_start) -> appointment id, or "EXTERNAL" for slots booked by other patients
    taken: dict[tuple[str, str], str] = field(default_factory=dict)
    idempotency: dict[str, str] = field(default_factory=dict)
    next_id: int = 1001


def seed() -> State:
    s = State()
    today = NOW.date()

    def add_appt(doctor_id: str, start: datetime, name: str, phone: str) -> str:
        appt_id = f"A{s.next_id}"
        s.next_id += 1
        s.appointments[appt_id] = {
            "id": appt_id,
            "doctor_id": doctor_id,
            "start": iso(start),
            "patient_name": name,
            "phone": phone,
            "status": "booked",
            "created_at": iso(NOW - timedelta(days=3)),
        }
        s.taken[(doctor_id, iso(start))] = appt_id
        return appt_id

    # Known patients (used by the eval scenarios)
    add_appt("d3", _dt(today + timedelta(days=1), 10, 30), "Priya Nair", "9876543210")   # A1001, Wed
    add_appt("d1", _dt(today, 12, 0), "Arjun Desai", "9123456780")                       # A1002, today, < 4h away
    add_appt("d5", _dt(today + timedelta(days=2), 17, 30), "Fatima Sheikh", "9988776655")  # A1003, Thu

    s.bills = {
        "B1": {"id": "B1", "phone": "9876543210", "amount_inr": 500, "description": "Consultation, Dr. Sunita Iyer",
               "date": "2026-11-20", "status": "unpaid"},
        "B2": {"id": "B2", "phone": "9123456780", "amount_inr": 1200, "description": "Skin biopsy",
               "date": "2026-11-10", "status": "paid"},
        "B3": {"id": "B3", "phone": "9123456780", "amount_inr": 350, "description": "Blood test (CBC)",
               "date": "2026-11-28", "status": "unpaid"},
    }

    # Dr. Mehta is fully booked on Friday evening (a scenario relies on this).
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    for t in all_slot_starts(friday):
        if t.hour >= 17:
            s.taken.setdefault(("d1", iso(t)), "EXTERNAL")

    # Fill about a quarter of the remaining slots with other patients, deterministically.
    # Some slots are kept free so the scenarios always have something to offer.
    keep_free = {
        ("d2", friday),                          # Dr. Rao, Friday: free all day
        ("d3", today + timedelta(days=6)),       # Dr. Iyer, next Monday
        ("d4", today + timedelta(days=2)),       # Dr. Sharma, Thursday
        ("d5", today + timedelta(days=1)),       # Dr. Khan, Wednesday
        ("d5", today + timedelta(days=4)),       # Dr. Khan, Saturday
    }
    rng = random.Random(42)
    for doc in DOCTORS:
        for offset in range(DAYS_AHEAD):
            d = today + timedelta(days=offset)
            if (doc["id"], d) in keep_free:
                continue
            for t in all_slot_starts(d):
                if rng.random() < 0.25:
                    s.taken.setdefault((doc["id"], iso(t)), "EXTERNAL")
    return s
