"""The naive agent: one prompt, every tool, one loop.

It works on a good day. It has many problems on a bad one, and finding them is
part of the assignment. Replace it with agents built on your agentcore package.
"""

import json
import uuid

import anthropic

from . import hospital_client as hospital
from .schemas import ChatRequest, ChatResponse

MODEL = "claude-sonnet-5-5"

SYSTEM = """You are the friendly front desk assistant for City Care Hospital, Pune.
Help patients book, reschedule and cancel appointments, check bills and get payment links.
Keep replies short, like WhatsApp messages."""

TOOLS = [
    {
        "name": "find_doctors",
        "description": "List doctors, optionally filtered by specialty.",
        "input_schema": {"type": "object", "properties": {"specialty": {"type": "string"}}},
    },
    {
        "name": "free_slots",
        "description": "Free 30-minute slots for a doctor on a date (YYYY-MM-DD).",
        "input_schema": {
            "type": "object",
            "properties": {"doctor_id": {"type": "string"}, "date": {"type": "string"}},
            "required": ["doctor_id", "date"],
        },
    },
    {
        "name": "list_appointments",
        "description": "List appointments for a phone number.",
        "input_schema": {"type": "object", "properties": {"phone": {"type": "string"}}, "required": ["phone"]},
    },
    {
        "name": "book",
        "description": "Book a slot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "string"},
                "start": {"type": "string"},
                "patient_name": {"type": "string"},
                "phone": {"type": "string"},
            },
            "required": ["doctor_id", "start", "patient_name", "phone"],
        },
    },
    {
        "name": "reschedule",
        "description": "Move an appointment to a new start time.",
        "input_schema": {
            "type": "object",
            "properties": {"appointment_id": {"type": "string"}, "new_start": {"type": "string"}},
            "required": ["appointment_id", "new_start"],
        },
    },
    {
        "name": "cancel",
        "description": "Cancel an appointment.",
        "input_schema": {"type": "object", "properties": {"appointment_id": {"type": "string"}}, "required": ["appointment_id"]},
    },
    {
        "name": "list_bills",
        "description": "List bills for a phone number.",
        "input_schema": {"type": "object", "properties": {"phone": {"type": "string"}}, "required": ["phone"]},
    },
    {
        "name": "payment_link",
        "description": "Create a payment link for a bill.",
        "input_schema": {"type": "object", "properties": {"bill_id": {"type": "string"}}, "required": ["bill_id"]},
    },
]

HISTORY: dict[str, list] = {}


def get_client():
    """Tests replace this with a fake client."""
    return anthropic.Anthropic()


def run_tool(name: str, args: dict):
    return getattr(hospital, name)(**args)


async def handle(req: ChatRequest) -> ChatResponse:
    client = get_client()
    messages = HISTORY.setdefault(req.session_id, [])
    messages.append({"role": "user", "content": f"(Patient's phone: {req.phone})\n{req.message}"})

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=4096, system=SYSTEM, tools=TOOLS, messages=messages
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            break
        results = []
        for block in response.content:
            if block.type == "tool_use":
                output = run_tool(block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(output)})
        messages.append({"role": "user", "content": results})

    reply = "".join(b.text for b in response.content if b.type == "text")
    return ChatResponse(reply=reply, agent="naive", trace_id=str(uuid.uuid4()))
