import json

import pytest

from hakiki import Ledger, generate_keypair


@pytest.fixture
def keys():
    return generate_keypair()


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "run.jsonl"


@pytest.fixture
def make_log(keys, log_path):
    """Write a small log of ``n`` tool calls (2 entries each) and return its path."""

    def _make(n=3, **opts):
        ledger = Ledger(log_path, keys[0], agent="test-agent", model="test-model", actor="tester", **opts)

        @ledger.tool
        def add(a, b):
            return a + b

        for i in range(n):
            add(i, i)
        return ledger

    return _make


def read_lines(path):
    return path.read_bytes().splitlines(keepends=True)


def write_lines(path, lines):
    path.write_bytes(b"".join(lines))


def load(line):
    return json.loads(line)


def dump(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()
