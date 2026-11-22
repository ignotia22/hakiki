"""Record and run tool calls from OpenAI and Anthropic tool-use responses.

Neither SDK is imported: responses can be SDK objects or plain dicts.
``tools`` maps tool names to Python functions. Functions already decorated
with ``@ledger.tool`` keep their approval settings; plain functions are run
through ``ledger.call``. Errors and rejections are recorded in the log and
returned to the model as error results rather than raised.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from .ledger import ApprovalRejected, Ledger


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def _run_one(ledger: Ledger, tools: Mapping[str, Callable], name: str, args: Any) -> tuple[str, bool]:
    """Run one tool call; return ``(content, is_error)``."""
    fn = tools.get(name)
    if fn is None or not isinstance(args, dict):
        error = "UnknownTool" if fn is None else "InvalidArguments"
        ledger._append("tool_error", {"tool": name, "error": error})
        return f"Error: {error} for tool {name!r}", True
    try:
        if getattr(fn, "__hakiki_ledger__", None) is not None:
            result = fn(**args)
        else:
            result = ledger.call(name, fn, args)
    except ApprovalRejected as exc:
        return f"Not run: {exc}", True
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}", True
    return _as_text(result), False


def _parse_json_args(raw: Any) -> Any:
    if isinstance(raw, (dict, type(None))):
        return raw or {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def run_openai_tool_calls(ledger: Ledger, response: Any, tools: Mapping[str, Callable]) -> list:
    """Run the tool calls in an OpenAI response through the ledger.

    Accepts a Chat Completions response (or its ``message``) and returns
    ``{"role": "tool", ...}`` messages, or a Responses API response and
    returns ``{"type": "function_call_output", ...}`` items.
    """
    output = _get(response, "output")
    if output is not None:  # Responses API
        results = []
        for item in output:
            if _get(item, "type") != "function_call":
                continue
            content, _ = _run_one(ledger, tools, _get(item, "name"), _parse_json_args(_get(item, "arguments")))
            results.append({"type": "function_call_output", "call_id": _get(item, "call_id"), "output": content})
        return results

    choices = _get(response, "choices")
    message = _get(choices[0], "message") if choices else response
    results = []
    for call in _get(message, "tool_calls") or []:
        fn = _get(call, "function")
        content, _ = _run_one(ledger, tools, _get(fn, "name"), _parse_json_args(_get(fn, "arguments")))
        results.append({"role": "tool", "tool_call_id": _get(call, "id"), "content": content})
    return results


def run_anthropic_tool_uses(ledger: Ledger, response: Any, tools: Mapping[str, Callable]) -> list:
    """Run the ``tool_use`` blocks of an Anthropic Messages response through the ledger.

    Returns ``tool_result`` content blocks to send back in the next user message.
    """
    results = []
    for block in _get(response, "content") or []:
        if _get(block, "type") != "tool_use":
            continue
        content, is_error = _run_one(ledger, tools, _get(block, "name"), _get(block, "input") or {})
        result = {"type": "tool_result", "tool_use_id": _get(block, "id"), "content": content}
        if is_error:
            result["is_error"] = True
        results.append(result)
    return results


__all__ = ["run_openai_tool_calls", "run_anthropic_tool_uses"]
