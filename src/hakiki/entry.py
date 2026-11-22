"""Entry format: canonical JSON, hashing and signing."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

FORMAT_VERSION = 1
GENESIS_HASH = "0" * 64
ENTRY_TYPES = ("tool_call", "tool_result", "tool_error", "approval", "note", "checkpoint")
REQUIRED_FIELDS = (
    "v", "seq", "ts", "log_id", "prev_hash", "agent", "model", "actor",
    "type", "data", "key_id", "hash", "sig",
)


def canonical(obj: Any) -> bytes:
    """Canonical JSON: sorted keys, compact separators, UTF-8."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def entry_hash(entry: dict) -> str:
    """SHA-256 over the entry's canonical JSON, excluding ``hash`` and ``sig``."""
    body = {k: v for k, v in entry.items() if k not in ("hash", "sig")}
    return sha256_hex(canonical(body))


def sign_entry(entry: dict, private_key) -> dict:
    """Fill in ``hash`` and ``sig`` (Ed25519 over the hash's ASCII hex)."""
    entry["hash"] = entry_hash(entry)
    entry["sig"] = private_key.sign(entry["hash"].encode("ascii")).hex()
    return entry


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
