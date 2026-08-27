"""OpenAI response-text extraction unit contracts."""

from types import SimpleNamespace

from rlm.backends.openai import responses_text


def test_responses_text_uses_output_text():
    resp = SimpleNamespace(output_text="hello from helper", output=[])
    assert responses_text(resp) == "hello from helper"


def test_responses_text_walks_message_content():
    part = SimpleNamespace(type="output_text", text="```python\nFINAL('x')\n```")
    msg = SimpleNamespace(type="message", content=[part])
    resp = SimpleNamespace(output_text="", output=[msg])
    assert "FINAL" in responses_text(resp)


def test_responses_text_skips_reasoning():
    thought = SimpleNamespace(type="reasoning", content=["secret chain"])
    resp = SimpleNamespace(output_text="", output=[thought])
    assert responses_text(resp) == ""
