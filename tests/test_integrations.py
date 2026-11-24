"""Integrations are tested with fake response objects: no SDKs, no network."""

import json
from types import SimpleNamespace as NS

from hakiki import INTACT, Approval, Ledger, verify
from hakiki.integrations import run_anthropic_tool_uses, run_openai_tool_calls


def get_weather(city):
    return {"city": city, "temp_c": 21}


def types(log_path, keys):
    result = verify(log_path, keys[1])
    assert result.status == INTACT
    return [(e["type"], e["data"].get("tool")) for e in result.entries]


def test_openai_chat_completions_sdk_objects(keys, log_path):
    ledger = Ledger(log_path, keys[0])
    call = NS(id="call_1", type="function", function=NS(name="get_weather", arguments='{"city": "Nairobi"}'))
    response = NS(choices=[NS(message=NS(role="assistant", content=None, tool_calls=[call]))])
    out = run_openai_tool_calls(ledger, response, {"get_weather": get_weather})
    assert out == [{"role": "tool", "tool_call_id": "call_1", "content": json.dumps({"city": "Nairobi", "temp_c": 21})}]
    assert types(log_path, keys) == [("tool_call", "get_weather"), ("tool_result", "get_weather")]


def test_openai_dicts_and_unknown_tool(keys, log_path):
    ledger = Ledger(log_path, keys[0])
    response = {"choices": [{"message": {"tool_calls": [
        {"id": "a", "function": {"name": "get_weather", "arguments": '{"city": "Lagos"}'}},
        {"id": "b", "function": {"name": "launch_rocket", "arguments": "{}"}},
        {"id": "c", "function": {"name": "get_weather", "arguments": "not json"}},
    ]}}]}
    out = run_openai_tool_calls(ledger, response, {"get_weather": get_weather})
    assert [o["tool_call_id"] for o in out] == ["a", "b", "c"]
    assert "UnknownTool" in out[1]["content"]
    assert "InvalidArguments" in out[2]["content"]
    assert types(log_path, keys)[-2:] == [("tool_error", "launch_rocket"), ("tool_error", "get_weather")]


def test_openai_responses_api(keys, log_path):
    ledger = Ledger(log_path, keys[0])
    response = NS(output=[
        NS(type="message", content=[]),
        NS(type="function_call", call_id="fc_1", name="get_weather", arguments='{"city": "Accra"}'),
    ])
    out = run_openai_tool_calls(ledger, response, {"get_weather": get_weather})
    assert out[0]["type"] == "function_call_output" and out[0]["call_id"] == "fc_1"
    assert "Accra" in out[0]["output"]


def test_openai_no_tool_calls(keys, log_path):
    ledger = Ledger(log_path, keys[0])
    assert run_openai_tool_calls(ledger, NS(choices=[NS(message=NS(tool_calls=None))]), {}) == []


def test_anthropic_sdk_objects_with_approval(keys, log_path):
    ledger = Ledger(log_path, keys[0])

    @ledger.tool(requires_approval=True, approver=lambda t, a: Approval("rejected", "ops@example.com", "not today"))
    def refund(amount):
        raise AssertionError("must not run")

    response = NS(stop_reason="tool_use", content=[
        NS(type="text", text="Let me check."),
        NS(type="tool_use", id="toolu_1", name="get_weather", input={"city": "Kampala"}),
        NS(type="tool_use", id="toolu_2", name="refund", input={"amount": 50}),
    ])
    out = run_anthropic_tool_uses(ledger, response, {"get_weather": get_weather, "refund": refund})
    assert out[0] == {"type": "tool_result", "tool_use_id": "toolu_1", "content": json.dumps({"city": "Kampala", "temp_c": 21})}
    assert out[1]["is_error"] is True and "not today" in out[1]["content"]
    assert types(log_path, keys) == [
        ("tool_call", "get_weather"), ("tool_result", "get_weather"), ("approval", "refund"),
    ]


def test_anthropic_dicts_and_tool_error(keys, log_path):
    ledger = Ledger(log_path, keys[0])

    def flaky():
        raise TimeoutError("upstream")

    response = {"content": [{"type": "tool_use", "id": "t1", "name": "flaky", "input": {}}]}
    out = run_anthropic_tool_uses(ledger, response, {"flaky": flaky})
    assert out[0]["is_error"] is True and "TimeoutError" in out[0]["content"]
    assert types(log_path, keys) == [("tool_call", "flaky"), ("tool_error", "flaky")]


# The JSON body an OpenAI-compatible chat-completions endpoint returns,
# exactly as it arrives over HTTP: arguments are a JSON string, content may
# be empty, and several tool calls can come back at once.
OPENAI_COMPATIBLE_BODY = """
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1764000000,
  "model": "local-model",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [
          {"id": "call_a", "index": 0, "type": "function",
           "function": {"name": "get_weather", "arguments": "{\\"city\\": \\"Mombasa\\"}"}},
          {"id": "call_b", "index": 1, "type": "function",
           "function": {"name": "get_weather", "arguments": "{\\"city\\": \\"Kisumu\\"}"}}
        ]
      },
      "finish_reason": "tool_calls"
    }
  ],
  "usage": {"prompt_tokens": 80, "completion_tokens": 30, "total_tokens": 110}
}
"""


def test_openai_compatible_chat_completions_json(keys, log_path):
    ledger = Ledger(log_path, keys[0], model="local-model")
    response = json.loads(OPENAI_COMPATIBLE_BODY)
    out = run_openai_tool_calls(ledger, response, {"get_weather": get_weather})
    assert out == [
        {"role": "tool", "tool_call_id": "call_a", "content": json.dumps({"city": "Mombasa", "temp_c": 21})},
        {"role": "tool", "tool_call_id": "call_b", "content": json.dumps({"city": "Kisumu", "temp_c": 21})},
    ]
    assert types(log_path, keys) == [("tool_call", "get_weather"), ("tool_result", "get_weather")] * 2
