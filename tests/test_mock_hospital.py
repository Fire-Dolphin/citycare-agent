"""Tests for the mock hospital system. They also show how it behaves under chaos."""

import pytest
from fastapi.testclient import TestClient

from mock_hospital.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_state():
    client.post("/_admin/reset")
    client.post("/_admin/chaos", json={})  # chaos off
    yield
    client.post("/_admin/chaos", json={})


def test_clock_is_fixed():
    assert client.get("/now").json()["now"] == "2026-12-01T09:00:00+05:30"


def test_dr_mehta_is_full_on_friday_evening_but_dr_rao_is_free():
    mehta = client.get("/doctors/d1/slots", params={"date": "2026-12-04"}).json()["free"]
    rao = client.get("/doctors/d2/slots", params={"date": "2026-12-04"}).json()["free"]
    assert not [s for s in mehta if s[11:13] >= "17"]
    assert "2026-12-04T17:00:00+05:30" in rao


def test_book_then_slot_disappears():
    body = {"doctor_id": "d2", "start": "2026-12-04T17:00:00+05:30", "patient_name": "Test", "phone": "9000000099"}
    assert client.post("/appointments", json=body).status_code == 201
    assert client.post("/appointments", json=body).json()["error"] == "slot_taken"


def test_idempotency_key_makes_retries_safe():
    body = {"doctor_id": "d2", "start": "2026-12-04T17:30:00+05:30", "patient_name": "Test",
            "phone": "9000000099", "idempotency_key": "abc-123"}
    first = client.post("/appointments", json=body)
    again = client.post("/appointments", json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"]


def test_commit_then_fail_still_saves_the_booking():
    client.post("/_admin/chaos", json={"commit_then_fail_next": 1})
    body = {"doctor_id": "d5", "start": "2026-12-02T17:00:00+05:30", "patient_name": "Test", "phone": "9000000099"}
    assert client.post("/appointments", json=body).status_code == 503
    booked = client.get("/appointments", params={"phone": "9000000099"}).json()["appointments"]
    assert len(booked) == 1  # it was saved even though the call "failed"


def test_lost_race_returns_409():
    client.post("/_admin/chaos", json={"race_next": 1})
    body = {"doctor_id": "d4", "start": "2026-12-03T11:00:00+05:30", "patient_name": "Test", "phone": "9000000099"}
    assert client.post("/appointments", json=body).status_code == 409


def test_system_does_not_check_who_is_asking():
    # Anyone can cancel anyone's appointment. Your agent must stop this.
    assert client.post("/appointments/A1001/cancel").status_code == 200


def test_bad_phone_is_rejected():
    body = {"doctor_id": "d2", "start": "2026-12-04T18:00:00+05:30", "patient_name": "Test", "phone": "12345"}
    assert client.post("/appointments", json=body).json()["error"] == "invalid_phone"
