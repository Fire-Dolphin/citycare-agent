"""Example of testing an agent without an API key, using FakeClaude.

These pass against the naive agent. Write your own for agentcore and your agents.
"""

import asyncio

from agent_service import naive_agent
from agent_service.schemas import ChatRequest
from tests.fake_claude import FakeClaude, text, tool_use


def _chat(message: str, session_id: str = "s1"):
    return asyncio.run(naive_agent.handle(ChatRequest(session_id=session_id, phone="9000000001", message=message)))


def test_plain_reply(monkeypatch):
    fake = FakeClaude([text("Hello! How can I help?")])
    monkeypatch.setattr(naive_agent, "get_client", lambda: fake)
    naive_agent.HISTORY.clear()

    res = _chat("hi")

    assert res.reply == "Hello! How can I help?"
    assert len(fake.messages.calls) == 1


def test_tool_call_then_reply(monkeypatch):
    fake = FakeClaude([
        tool_use("find_doctors", {"specialty": "Dermatology"}),
        text("Dr. Mehta and Dr. Rao are our skin doctors."),
    ])
    monkeypatch.setattr(naive_agent, "get_client", lambda: fake)
    monkeypatch.setattr(naive_agent.hospital, "find_doctors",
                        lambda specialty=None: {"doctors": [{"id": "d1"}, {"id": "d2"}]})
    naive_agent.HISTORY.clear()

    res = _chat("skin doctor?", session_id="s2")

    assert "Dr. Rao" in res.reply
    second_request = fake.messages.calls[1]["messages"]
    assert second_request[-1]["content"][0]["type"] == "tool_result"
