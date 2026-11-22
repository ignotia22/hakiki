"""Verification: check a log's hashes, chain, signatures and checkpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from cryptography.exceptions import InvalidSignature

from .checkpoint import checkpoint_problem, read_checkpoints
from .entry import ENTRY_TYPES, FORMAT_VERSION, GENESIS_HASH, REQUIRED_FIELDS, entry_hash
from .keys import as_public_key, key_id

INTACT, TAMPERED, INCOMPLETE = "INTACT", "TAMPERED", "INCOMPLETE"
EXIT_CODES = {INTACT: 0, TAMPERED: 1, INCOMPLETE: 2}

EXPLANATIONS = {
    INTACT: "Every entry is genuine and in its original order: nothing was edited, added, "
    "removed or reordered after it was written{ckpt}.",
    TAMPERED: "This log was changed after it was written: at least one entry was edited, added, "
    "removed, reordered or signed with the wrong key, so it cannot be relied on.",
    INCOMPLETE: "The entries that remain are genuine, but some are missing: the log is shorter "
    "than, or differs from, what an earlier checkpoint recorded.",
}


@dataclass
class VerifyResult:
    status: str
    problems: list = field(default_factory=list)
    entries: list = field(default_factory=list)
    checkpoints_checked: int = 0
    key_id: str = ""

    @property
    def ok(self) -> bool:
        return self.status == INTACT

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]

    @property
    def explanation(self) -> str:
        if self.status == INCOMPLETE and not self.entries:
            return "The log contains no entries, so there is nothing to vouch for."
        ckpt = ""
        if self.status == INTACT:
            n = self.checkpoints_checked
            ckpt = (
                f", and it matches {n} checkpoint{'s' if n != 1 else ''}"
                if n
                else ". No checkpoints were checked, so entries deleted from the end "
                "would not be detected"
            )
        return EXPLANATIONS[self.status].format(ckpt=ckpt)

    def __bool__(self) -> bool:
        return self.ok


def read_log(path) -> tuple[list, list]:
    """Return ``(entries, problems)``. Lines that are not valid JSON become problems."""
    entries, problems = [], []
    with open(path, "rb") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                problems.append(f"line {lineno}: not valid JSON")
                continue
            if not isinstance(obj, dict):
                problems.append(f"line {lineno}: not a log entry")
                continue
            entries.append(obj)
    return entries, problems


def _entry_problems(i: int, entry: dict, prev: Optional[dict], public_key, kid: str) -> list:
    where = f"entry {i + 1}"
    missing = [f for f in REQUIRED_FIELDS if f not in entry]
    if missing:
        return [f"{where}: missing field(s) {', '.join(missing)}"]
    out = []
    if entry["v"] != FORMAT_VERSION:
        out.append(f"{where}: unknown format version {entry['v']!r}")
    if entry["seq"] != i:
        out.append(f"{where}: sequence number is {entry['seq']!r}, expected {i}")
    if entry["type"] not in ENTRY_TYPES:
        out.append(f"{where}: unknown entry type {entry['type']!r}")
    if prev is not None and entry["log_id"] != prev["log_id"]:
        out.append(f"{where}: belongs to a different log")
    expected_prev = GENESIS_HASH if prev is None else prev.get("hash")
    if entry["prev_hash"] != expected_prev:
        out.append(f"{where}: does not link to the entry before it")
    try:
        edited = entry_hash(entry) != entry["hash"]
    except ValueError:
        edited = True
    if edited:
        out.append(f"{where}: contents do not match its hash (edited)")
    if entry["key_id"] != kid:
        out.append(f"{where}: signed by a different key ({entry['key_id']})")
    else:
        try:
            public_key.verify(bytes.fromhex(entry["sig"]), str(entry["hash"]).encode("ascii"))
        except (InvalidSignature, ValueError, TypeError, UnicodeEncodeError):
            out.append(f"{where}: signature is not valid")
    return out


def verify(log_path, public_key, checkpoints=None) -> VerifyResult:
    """Verify a log against a public key supplied by the caller.

    The key stored in the log is never trusted. ``checkpoints`` is an optional
    path to a checkpoints file kept somewhere the operator cannot edit.
    """
    public_key = as_public_key(public_key)
    kid = key_id(public_key)
    entries, problems = read_log(log_path)
    tampered = list(problems)
    for i, entry in enumerate(entries):
        tampered += _entry_problems(i, entry, entries[i - 1] if i else None, public_key, kid)

    incomplete, checked = [], 0
    if not entries:
        incomplete.append("the log has no entries")
    if checkpoints is not None:
        log_id = entries[0].get("log_id") if entries else None
        cps = read_checkpoints(checkpoints)
        for n, cp in enumerate(cps, 1):
            why = checkpoint_problem(cp, public_key) if cp is not None else "is not valid JSON"
            if why:
                tampered.append(f"checkpoint {n} {why}")
                continue
            if cp["log_id"] != log_id:
                continue  # a checkpoint for another log in the same file
            checked += 1
            seq = cp["seq"]
            if seq >= len(entries):
                incomplete.append(
                    f"checkpoint {n} shows the log reached {cp['count']} entries, "
                    f"but only {len(entries)} remain"
                )
            elif entries[seq].get("hash") != cp["head_hash"]:
                incomplete.append(f"checkpoint {n} does not match entry {seq + 1}")
        if entries and cps and not checked and not tampered:
            incomplete.append("none of the checkpoints belong to this log (it may have been replaced)")

    status = TAMPERED if tampered else INCOMPLETE if incomplete else INTACT
    return VerifyResult(status, tampered + incomplete, entries, checked, kid)
