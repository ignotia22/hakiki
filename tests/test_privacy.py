import pytest

from hakiki import INTACT, Ledger, verify

SECRETS = ["4111-1111-1111-1111", "Hunter2-password", "jane.doe@private.example", "Tilbury Road 17"]


def test_default_mode_never_stores_raw_values(keys, log_path):
    ledger = Ledger(log_path, keys[0])

    @ledger.tool
    def charge(card, password, customer):
        return {"receipt_for": customer, "address": SECRETS[3]}

    @ledger.tool
    def fail(card):
        raise ValueError(f"card {card} declined")

    charge(SECRETS[0], password=SECRETS[1], customer=SECRETS[2])
    with pytest.raises(ValueError):
        fail(SECRETS[0])

    raw = log_path.read_bytes()
    for secret in SECRETS:
        assert secret.encode() not in raw
        assert secret.encode().hex().encode() not in raw
    assert verify(log_path, keys[1]).status == INTACT

    call = verify(log_path, keys[1]).entries[0]["data"]["args"]
    assert set(call) == {"sha256", "summary"}
    assert call["summary"] == {"type": "dict", "len": 3, "keys": ["card", "customer", "password"]}


def test_full_mode_with_redaction(keys, log_path):
    ledger = Ledger(log_path, keys[0], capture="full", redact=["password", "API_KEY"])

    @ledger.tool
    def login(user, password, options):
        return {"token_for": user, "api_key": "sk-live-123"}

    login("sam", password="Hunter2-password", options={"Api_Key": "sk-nested-456", "retries": 2})
    raw = log_path.read_bytes()
    for secret in (b"Hunter2-password", b"sk-live-123", b"sk-nested-456"):
        assert secret not in raw
    log = verify(log_path, keys[1]).entries
    assert log[0]["data"]["args"] == {"user": "sam", "options": {"retries": 2}}
    assert log[1]["data"]["result"] == {"token_for": "sam"}


def test_redacted_keys_do_not_affect_the_hash(keys, tmp_path):
    hashes = []
    for i, pw in enumerate(["one", "two"]):
        ledger = Ledger(tmp_path / f"{i}.jsonl", keys[0], redact=["password"])
        ledger.call("login", lambda user, password: None, {"user": "sam", "password": pw})
        hashes.append(verify(tmp_path / f"{i}.jsonl", keys[1]).entries[0]["data"]["args"]["sha256"])
    assert hashes[0] == hashes[1]


def test_odd_values_are_captured(keys, log_path):
    ledger = Ledger(log_path, keys[0], capture="full")
    ledger.call("t", lambda **kw: b"\x00bytes", {"f": float("nan"), "s": {3, 1}, "o": object()})
    assert verify(log_path, keys[1]).status == INTACT
