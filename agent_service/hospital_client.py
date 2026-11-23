"""Thin client for the mock hospital system. No retries, no timeouts, no idempotency."""

import os

import httpx

BASE = os.getenv("HOSPITAL_URL", "http://localhost:8001")


def _get(path: str, **params):
    r = httpx.get(f"{BASE}{path}", params=params)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict | None = None):
    r = httpx.post(f"{BASE}{path}", json=body or {})
    r.raise_for_status()
    return r.json()


def find_doctors(specialty: str | None = None):
    return _get("/doctors", **({"specialty": specialty} if specialty else {}))


def free_slots(doctor_id: str, date: str):
    return _get(f"/doctors/{doctor_id}/slots", date=date)


def list_appointments(phone: str):
    return _get("/appointments", phone=phone)


def book(doctor_id: str, start: str, patient_name: str, phone: str):
    return _post("/appointments", {"doctor_id": doctor_id, "start": start, "patient_name": patient_name, "phone": phone})


def reschedule(appointment_id: str, new_start: str):
    return _post(f"/appointments/{appointment_id}/reschedule", {"new_start": new_start})


def cancel(appointment_id: str):
    return _post(f"/appointments/{appointment_id}/cancel")


def list_bills(phone: str):
    return _get("/bills", phone=phone)


def payment_link(bill_id: str):
    return _post(f"/bills/{bill_id}/payment-link")
