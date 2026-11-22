"""Attack the log: every change below must be caught."""

import random

from conftest import dump, load, read_lines, write_lines

from hakiki import TAMPERED, INTACT, Ledger, generate_keypair, verify
from hakiki.entry import sign_entry


def test_untouched_log_is_intact(make_log, keys, log_path):
    make_log(3)
    result = verify(log_path, keys[1])
    assert result.status == INTACT
    assert result.exit_code == 0
    assert len(result.entries) == 6
    assert result.problems == []


def test_editing_a_field_is_caught(make_log, keys, log_path):
    make_log(3)
    lines = read_lines(log_path)
    entry = load(lines[2])
    entry["agent"] = "someone-else"
    lines[2] = dump(entry)
    write_lines(log_path, lines)
    result = verify(log_path, keys[1])
    assert result.status == TAMPERED
    assert result.exit_code == 1
    assert any("entry 3" in p and "edited" in p for p in result.problems)


def test_editing_and_rehashing_without_the_key_is_caught(make_log, keys, log_path):
    from hakiki.entry import entry_hash

    make_log(3)
    lines = read_lines(log_path)
    entry = load(lines[-1])
    entry["data"]["tool"] = "something_harmless"
    entry["hash"] = entry_hash(entry)
    lines[-1] = dump(entry)
    write_lines(log_path, lines)
    result = verify(log_path, keys[1])
    assert result.status == TAMPERED
    assert any("signature" in p for p in result.problems)


def test_deleting_a_middle_entry_is_caught(make_log, keys, log_path):
    make_log(3)
    lines = read_lines(log_path)
    del lines[2]
    write_lines(log_path, lines)
    result = verify(log_path, keys[1])
    assert result.status == TAMPERED
    assert any("does not link" in p for p in result.problems)


def test_reordering_entries_is_caught(make_log, keys, log_path):
    make_log(3)
    lines = read_lines(log_path)
    lines[1], lines[3] = lines[3], lines[1]
    write_lines(log_path, lines)
    assert verify(log_path, keys[1]).status == TAMPERED


def test_inserting_an_entry_is_caught(make_log, keys, log_path):
    make_log(3)
    lines = read_lines(log_path)
    lines.insert(2, lines[1])  # replay a genuine, correctly signed entry
    write_lines(log_path, lines)
    assert verify(log_path, keys[1]).status == TAMPERED


def test_inserting_a_forged_entry_is_caught(make_log, keys, log_path):
    make_log(3)
    lines = read_lines(log_path)
    forged = load(lines[1])
    forged["data"] = {"tool": "approve_refund"}
    attacker_key, _ = generate_keypair()
    sign_entry(forged, attacker_key)  # keeps the victim's key_id
    lines.insert(2, dump(forged))
    write_lines(log_path, lines)
    result = verify(log_path, keys[1])
    assert result.status == TAMPERED
    assert any("signature" in p for p in result.problems)


def test_forged_signature_is_caught(make_log, keys, log_path):
    make_log(3)
    lines = read_lines(log_path)
    entry = load(lines[0])
    entry["sig"] = random.randbytes(64).hex()
    lines[0] = dump(entry)
    write_lines(log_path, lines)
    result = verify(log_path, keys[1])
    assert result.status == TAMPERED
    assert any("entry 1" in p and "signature" in p for p in result.problems)


def test_wrong_public_key_is_caught(make_log, log_path):
    make_log(3)
    _, other_pub = generate_keypair()
    result = verify(log_path, other_pub)
    assert result.status == TAMPERED
    assert any("different key" in p for p in result.problems)


def test_key_stored_in_log_is_never_trusted(make_log, keys, log_path):
    """Re-sign the whole log with an attacker key and matching key_id: still caught."""
    from hakiki import key_id

    make_log(3)
    attacker, attacker_pub = generate_keypair()
    lines = read_lines(log_path)
    prev = "0" * 64
    rewritten = []
    for line in lines:
        e = load(line)
        e["key_id"] = key_id(attacker_pub)
        e["prev_hash"] = prev
        sign_entry(e, attacker)
        prev = e["hash"]
        rewritten.append(dump(e))
    write_lines(log_path, rewritten)
    assert verify(log_path, attacker_pub).status == INTACT  # self-consistent forgery...
    assert verify(log_path, keys[1]).status == TAMPERED  # ...rejected by the real key


def test_garbage_line_is_caught(make_log, keys, log_path):
    make_log(2)
    with open(log_path, "ab") as f:
        f.write(b"{not json\n")
    assert verify(log_path, keys[1]).status == TAMPERED


def test_reopening_continues_the_chain(make_log, keys, log_path):
    first = make_log(2)
    again = Ledger(log_path, keys[0], agent="test-agent")
    assert again.log_id == first.log_id
    again.note("resumed")
    result = verify(log_path, keys[1])
    assert result.status == INTACT
    assert result.entries[-1]["seq"] == 4


def test_reopening_with_another_key_is_refused(make_log, log_path):
    import pytest

    make_log(1)
    other, _ = generate_keypair()
    with pytest.raises(ValueError):
        Ledger(log_path, other)


def test_tool_error_is_recorded_and_reraised(keys, log_path):
    import pytest

    ledger = Ledger(log_path, keys[0])

    @ledger.tool
    def boom():
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        boom()
    result = verify(log_path, keys[1])
    assert result.status == INTACT
    assert [e["type"] for e in result.entries] == ["tool_call", "tool_error"]
    assert result.entries[1]["data"]["error"] == "RuntimeError"
