"""Checkpoints: small signed records of how far a log had reached.

Stored somewhere the agent's operator cannot edit, they let ``verify`` notice
entries deleted from the end of a log, which the hash chain alone cannot.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from cryptography.exceptions import InvalidSignature

from .entry import FORMAT_VERSION, canonical, utc_now
from .keys import key_id

CHECKPOINT_FIELDS = ("v", "log_id", "seq", "head_hash", "count", "ts", "key_id", "sig")


def make_checkpoint(log_id: str, seq: int, head_hash: str, private_key) -> dict:
    """Return a signed checkpoint for a log whose last entry is ``seq``."""
    cp = {
        "v": FORMAT_VERSION,
        "log_id": log_id,
        "seq": seq,
        "head_hash": head_hash,
        "count": seq + 1,
        "ts": utc_now(),
        "key_id": key_id(private_key.public_key()),
    }
    cp["sig"] = private_key.sign(canonical(cp)).hex()
    return cp


def checkpoint_problem(cp: dict, public_key) -> Optional[str]:
    """Return why a checkpoint is invalid, or None if its signature checks out."""
    if not isinstance(cp, dict) or any(f not in cp for f in CHECKPOINT_FIELDS):
        return "is malformed"
    if not isinstance(cp["seq"], int) or isinstance(cp["seq"], bool) or cp["seq"] < 0:
        return "is malformed"
    if cp["key_id"] != key_id(public_key):
        return "was signed by a different key"
    body = {k: v for k, v in cp.items() if k != "sig"}
    try:
        public_key.verify(bytes.fromhex(cp["sig"]), canonical(body))
    except (InvalidSignature, ValueError, TypeError):
        return "has an invalid signature"
    if cp["count"] != cp["seq"] + 1:
        return "has an inconsistent count"
    return None


def append_checkpoint(cp: dict, path) -> None:
    with open(path, "ab") as f:
        f.write(canonical(cp) + b"\n")
        f.flush()
        os.fsync(f.fileno())


def read_checkpoints(path) -> list:
    """Read a checkpoints file. Unparseable lines come back as ``None``."""
    out = []
    with open(path, "rb") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line.decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                out.append(None)
    return out
