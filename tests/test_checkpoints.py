"""Checkpoints close the truncation gap that the hash chain leaves open."""

from conftest import dump, load, read_lines, write_lines

from hakiki import INCOMPLETE, INTACT, TAMPERED, Ledger, generate_keypair, verify
from hakiki.checkpoint import append_checkpoint, make_checkpoint, read_checkpoints


def test_truncation_without_checkpoint_is_missed(make_log, keys, log_path):
    """Documented limitation: dropping entries from the end leaves a valid chain."""
    make_log(3)
    write_lines(log_path, read_lines(log_path)[:-2])
    result = verify(log_path, keys[1])
    assert result.status == INTACT  # undetectable without a checkpoint
    assert "cannot be detected" in result.explanation


def test_truncation_with_checkpoint_is_caught(make_log, keys, log_path, tmp_path):
    cps = tmp_path / "checkpoints.jsonl"
    ledger = make_log(3)
    ledger.checkpoint(cps)
    assert verify(log_path, keys[1], cps).status == INTACT

    write_lines(log_path, read_lines(log_path)[:-3])
    result = verify(log_path, keys[1], cps)
    assert result.status == INCOMPLETE
    assert result.exit_code == 2
    assert any("only 4 remain" in p for p in result.problems)


def test_automatic_checkpoints(keys, log_path, tmp_path):
    cps = tmp_path / "checkpoints.jsonl"
    ledger = Ledger(log_path, keys[0], checkpoint_every=4, checkpoint_path=cps)
    for i in range(10):
        ledger.note(f"step {i}")
    written = read_checkpoints(cps)
    assert [c["count"] for c in written] == [4, 9]  # a checkpoint entry follows each one
    result = verify(log_path, keys[1], cps)
    assert result.status == INTACT
    assert result.checkpoints_checked == 2
    assert sum(e["type"] == "checkpoint" for e in result.entries) == 2


def test_tampered_checkpoint_is_caught(make_log, keys, log_path, tmp_path):
    cps = tmp_path / "checkpoints.jsonl"
    make_log(2).checkpoint(cps)
    lines = read_lines(cps)
    cp = load(lines[0])
    cp["seq"], cp["count"] = 1, 2  # pretend the log was shorter
    write_lines(cps, [dump(cp)])
    result = verify(log_path, keys[1], cps)
    assert result.status == TAMPERED
    assert any("checkpoint 1 has an invalid signature" in p for p in result.problems)


def test_checkpoint_signed_by_another_key_is_caught(make_log, keys, log_path, tmp_path):
    cps = tmp_path / "checkpoints.jsonl"
    ledger = make_log(2)
    other, _ = generate_keypair()
    append_checkpoint(make_checkpoint(ledger.log_id, 3, "f" * 64, other), cps)
    assert verify(log_path, keys[1], cps).status == TAMPERED


def test_operator_rewrite_after_checkpoint_is_caught(make_log, keys, log_path, tmp_path):
    """Someone holding the signing key rewrites history; the checkpoint disagrees."""
    from hakiki.entry import sign_entry

    cps = tmp_path / "checkpoints.jsonl"
    make_log(2).checkpoint(cps)
    lines = read_lines(log_path)
    prev, rewritten = "0" * 64, []
    for line in lines:
        e = load(line)
        if e["seq"] == 1:
            e["data"]["tool"] = "something_else"
        e["prev_hash"] = prev
        sign_entry(e, keys[0])
        prev = e["hash"]
        rewritten.append(dump(e))
    write_lines(log_path, rewritten)
    assert verify(log_path, keys[1]).status == INTACT  # the chain alone cannot tell
    result = verify(log_path, keys[1], cps)
    assert result.status == INCOMPLETE
    assert any("does not match entry" in p for p in result.problems)


def test_checkpoints_for_a_different_log(make_log, keys, log_path, tmp_path):
    cps = tmp_path / "checkpoints.jsonl"
    other = Ledger(tmp_path / "other.jsonl", keys[0])
    other.note("x")
    other.checkpoint(cps)
    make_log(1)
    result = verify(log_path, keys[1], cps)
    assert result.status == INCOMPLETE
    assert any("none of the checkpoints" in p for p in result.problems)


def test_empty_log_is_incomplete(keys, log_path):
    log_path.write_bytes(b"")
    result = verify(log_path, keys[1])
    assert result.status == INCOMPLETE
    assert "no entries" in result.explanation
