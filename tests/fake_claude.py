"""A scripted stand-in for anthropic.Anthropic, so tests run without an API key.

    fake = FakeClaude([
        tool_use("find_doctors", {"specialty": "Dermatology"}),
        text("Dr. Rao is free on Friday at 5pm. Shall I book it?"),
    ])
    response = fake.messages.create(model=..., messages=[...])   # returns the next scripted reply
    fake.messages.calls                                          # every request it received

Replies are real SDK objects (anthropic.types.Message), so code that reads
response.content, response.stop_reason and response.usage works unchanged.
Pass an Exception instance in the script to have create() raise it.
"""

from __future__ import annotations

import itertools

from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

_ids = itertools.count(1)


def _message(content: list, stop_reason: str, input_tokens: int = 100, output_tokens: int = 20) -> Message:
    return Message(
        id=f"msg_fake_{next(_ids)}",
        type="message",
        role="assistant",
        model="fake-model",
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def text(reply: str, stop_reason: str = "end_turn", **usage) -> Message:
    """A plain text reply. Use stop_reason="max_tokens" or "refusal" to test those paths."""
    return _message([TextBlock(type="text", text=reply)], stop_reason, **usage)


def tool_use(name: str, tool_input: dict, preamble: str | None = None, **usage) -> Message:
    """A reply that calls one tool."""
    blocks = [TextBlock(type="text", text=preamble)] if preamble else []
    blocks.append(ToolUseBlock(type="tool_use", id=f"toolu_fake_{next(_ids)}", name=name, input=tool_input))
    return _message(blocks, "tool_use", **usage)


def tool_uses(calls: list[tuple[str, dict]], **usage) -> Message:
    """A reply that calls several tools at once (parallel tool use)."""
    blocks = [ToolUseBlock(type="tool_use", id=f"toolu_fake_{next(_ids)}", name=n, input=i) for n, i in calls]
    return _message(blocks, "tool_use", **usage)


class _FakeMessages:
    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[dict] = []

    def create(self, **kwargs) -> Message:
        # Snapshot the message list: callers often keep appending to the same list.
        self.calls.append({**kwargs, "messages": list(kwargs.get("messages", []))})
        if not self.script:
            raise AssertionError("FakeClaude ran out of scripted replies")
        nxt = self.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class FakeClaude:
    def __init__(self, script: list):
        self.messages = _FakeMessages(script)
