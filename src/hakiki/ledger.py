"""The Ledger: records tool calls, results and approvals as signed log entries."""

from __future__ import annotations

import functools
import inspect
import json
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .checkpoint import append_checkpoint, make_checkpoint
from .entry import FORMAT_VERSION, GENESIS_HASH, canonical, sha256_hex, sign_entry, utc_now
from .keys import as_private_key, key_id

_MAX_DEPTH = 32


@dataclass(frozen=True)
class Approval:
    """A decision returned by an approver: ``status`` is "approved" or "rejected"."""

    status: str
    by: Optional[str] = None
    reason: str = ""

    def __post_init__(self):
        if self.status not in ("approved", "rejected"):
            raise ValueError('Approval status must be "approved" or "rejected"')


class ApprovalRejected(Exception):
    """Raised when a tool that requires approval was rejected or not approved."""

    def __init__(self, tool: str, approval: Optional[Approval] = None):
        self.tool = tool
        self.approval = approval
        if approval is None:
            detail = "no approval was given"
        else:
            detail = f"rejected by {approval.by or 'unknown'}"
            if approval.reason:
                detail += f": {approval.reason}"
        super().__init__(f"tool {tool!r} did not run: {detail}")


class Ledger:
    """Append-only, signed, hash-chained log of what an agent did.

    Two lines to add::

        ledger = Ledger("run.jsonl", key="hakiki.key", agent="my-agent", model="model-name")

        @ledger.tool
        def search(query): ...
    """

    def __init__(
        self,
        path,
        key,
        *,
        agent: str = "agent",
        model: Optional[str] = None,
        actor: Optional[str] = None,
        capture: str = "hash",
        redact: Iterable[str] = (),
        checkpoint_every: Optional[int] = None,
        checkpoint_path=None,
    ):
        if capture not in ("hash", "full"):
            raise ValueError('capture must be "hash" or "full"')
        if checkpoint_every is not None:
            if checkpoint_every < 1:
                raise ValueError("checkpoint_every must be a positive integer")
            if checkpoint_path is None:
                raise ValueError("checkpoint_every needs a checkpoint_path")
        self.path = Path(path)
        self._key = as_private_key(key)
        self.key_id = key_id(self._key.public_key())
        self.agent, self.model, self.actor = agent, model, actor
        self.capture = capture
        self.redact = {str(k).lower() for k in redact}
        self.checkpoint_every = checkpoint_every
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path is not None else None
        self._lock = threading.RLock()
        self._since_checkpoint = 0

        last = _last_entry(self.path)
        if last is None:
            self.log_id, self._seq, self._head = str(uuid.uuid4()), -1, GENESIS_HASH
        else:
            if last.get("key_id") != self.key_id:
                raise ValueError(f"{self.path} was written with a different key")
            self.log_id, self._seq, self._head = last["log_id"], last["seq"], last["hash"]

    # -- writing ---------------------------------------------------------

    def _append(self, type_: str, data: Any, approval: Optional[dict] = None) -> dict:
        with self._lock:
            entry = {
                "v": FORMAT_VERSION,
                "seq": self._seq + 1,
                "ts": utc_now(),
                "log_id": self.log_id,
                "prev_hash": self._head,
                "agent": self.agent,
                "model": self.model,
                "actor": self.actor,
                "type": type_,
                "data": data,
                "key_id": self.key_id,
            }
            if approval is not None:
                entry["approval"] = approval
            sign_entry(entry, self._key)
            with open(self.path, "ab") as f:
                f.write(canonical(entry) + b"\n")
                f.flush()
                os.fsync(f.fileno())
            self._seq, self._head = entry["seq"], entry["hash"]
            if type_ != "checkpoint" and self.checkpoint_every:
                self._since_checkpoint += 1
                if self._since_checkpoint >= self.checkpoint_every:
                    self.checkpoint()
            return entry

    def note(self, message: Any) -> dict:
        """Record a free-form note. Notes are stored as given (they are not hashed)."""
        return self._append("note", {"message": _clean(message, self.redact)})

    def approve(self, action: str, by: str, *, status: str = "approved", reason: str = "") -> dict:
        """Record a human approval (or rejection) made outside a tool call."""
        decision = Approval(status=status, by=by, reason=reason)
        return self._append(
            "approval",
            {"action": action},
            approval={"status": decision.status, "by": decision.by, "reason": decision.reason},
        )

    def checkpoint(self, path=None) -> dict:
        """Write a signed checkpoint of the current head to the checkpoints file."""
        path = Path(path) if path is not None else self.checkpoint_path
        if path is None:
            raise ValueError("no checkpoint path: pass one here or to Ledger(checkpoint_path=...)")
        with self._lock:
            if self._seq < 0:
                raise ValueError("cannot checkpoint an empty log")
            cp = make_checkpoint(self.log_id, self._seq, self._head, self._key)
            append_checkpoint(cp, path)
            self._since_checkpoint = 0
            self._append(
                "checkpoint",
                {"seq": cp["seq"], "head_hash": cp["head_hash"], "file": path.name},
            )
            return cp

    # -- tools -----------------------------------------------------------

    def tool(
        self,
        fn: Optional[Callable] = None,
        *,
        name: Optional[str] = None,
        approved_by: Optional[str] = None,
        requires_approval: bool = False,
        approver: Optional[Callable] = None,
    ):
        """Decorator that records each call of a tool, its result and its approval."""
        _check_approval_options(approved_by, requires_approval, approver)

        def decorate(f):
            if inspect.iscoroutinefunction(f):
                raise TypeError("async tools are not supported in this version")
            sig = inspect.signature(f)
            tool_name = name or f.__name__

            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                return self._run(
                    tool_name,
                    lambda: f(*args, **kwargs),
                    _bind(sig, args, kwargs),
                    approved_by,
                    requires_approval,
                    approver,
                )

            wrapper.__hakiki_ledger__ = self
            return wrapper

        return decorate(fn) if fn is not None else decorate

    def call(
        self,
        tool_name: str,
        fn: Callable,
        args: Optional[dict] = None,
        *,
        approved_by: Optional[str] = None,
        requires_approval: bool = False,
        approver: Optional[Callable] = None,
    ):
        """Run ``fn(**args)`` through the ledger without decorating it."""
        _check_approval_options(approved_by, requires_approval, approver)
        args = dict(args or {})
        return self._run(tool_name, lambda: fn(**args), args, approved_by, requires_approval, approver)

    def _run(self, tool_name, invoke, args, approved_by, requires_approval, approver):
        approval = None
        if requires_approval:
            error = None
            try:
                decision = approver(tool_name, dict(args))
            except Exception as exc:  # an approver that crashes is a "no"
                decision, error = None, exc
            if not (isinstance(decision, Approval) and decision.status == "approved"):
                given = decision if isinstance(decision, Approval) else None
                if given is not None:
                    reason = given.reason
                elif error is not None:
                    reason = f"approver raised {type(error).__name__}"
                else:
                    reason = "no approval was given"
                self._append(
                    "approval",
                    {"tool": tool_name, "args": self._capture(args)},
                    approval={"status": "rejected", "by": given.by if given else None, "reason": reason},
                )
                raise ApprovalRejected(tool_name, given) from error
            rec = self._append(
                "approval",
                {"tool": tool_name, "args": self._capture(args)},
                approval={"status": "approved", "by": decision.by, "reason": decision.reason},
            )
            approval = {"status": "approved", "by": decision.by, "ref_seq": rec["seq"]}
        elif approved_by:
            approval = {"status": "approved", "by": approved_by, "standing": True}

        call = self._append(
            "tool_call", {"tool": tool_name, "args": self._capture(args)}, approval=approval
        )
        start = time.perf_counter()
        try:
            result = invoke()
        except Exception as exc:
            self._append(
                "tool_error",
                {
                    "tool": tool_name,
                    "call_seq": call["seq"],
                    "error": type(exc).__name__,
                    "message": self._capture(str(exc)),
                    "ms": _ms(start),
                },
            )
            raise
        self._append(
            "tool_result",
            {"tool": tool_name, "call_seq": call["seq"], "result": self._capture(result), "ms": _ms(start)},
        )
        return result

    # -- privacy ---------------------------------------------------------

    def _capture(self, value: Any) -> Any:
        """Raw (redacted) value in "full" mode; hash plus summary in "hash" mode."""
        clean = _clean(value, self.redact)
        if self.capture == "full":
            return clean
        return {"sha256": sha256_hex(canonical(clean)), "summary": _summary(clean, value)}


# -- helpers -------------------------------------------------------------


def _check_approval_options(approved_by, requires_approval, approver):
    if requires_approval and approver is None:
        raise ValueError("requires_approval=True needs an approver function")
    if requires_approval and approved_by:
        raise ValueError("use either approved_by or requires_approval, not both")


def _bind(sig: inspect.Signature, args: tuple, kwargs: dict) -> dict:
    try:
        return dict(sig.bind(*args, **kwargs).arguments)
    except TypeError:
        return {"args": list(args), "kwargs": dict(kwargs)}


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _clean(value: Any, redact: set, depth: int = 0) -> Any:
    """Make a value JSON-safe, dropping any dict key named in ``redact``."""
    if depth > _MAX_DEPTH:
        return "<too deep>"
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, dict):
        return {
            str(k): _clean(v, redact, depth + 1)
            for k, v in value.items()
            if str(k).lower() not in redact
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=repr) if isinstance(value, (set, frozenset)) else value
        return [_clean(v, redact, depth + 1) for v in items]
    if isinstance(value, (bytes, bytearray)):
        return {"bytes_sha256": sha256_hex(bytes(value)), "len": len(value)}
    return repr(value)


def _summary(clean: Any, original: Any) -> dict:
    summary = {"type": type(original).__name__}
    if isinstance(clean, (str, list, dict)):
        summary["len"] = len(clean)
    if isinstance(clean, dict):
        summary["keys"] = sorted(clean)[:20]
    return summary


def _last_entry(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    last = None
    with open(path, "rb") as f:
        for line in f:
            if line.strip():
                last = line
    if last is None:
        return None
    try:
        return json.loads(last.decode("utf-8"))
    except ValueError as exc:
        raise ValueError(f"last line of {path} is not valid JSON; refusing to append") from exc
