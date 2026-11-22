import os
import subprocess
import sys

import pytest
from conftest import read_lines, write_lines

from hakiki import Ledger, load_private_key
from hakiki.cli import main


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["keygen", "--out", "k"]) == 0
    ledger = Ledger("run.jsonl", load_private_key("k.key"), agent="cli-test")
    for i in range(3):
        ledger.note(f"step {i}")
    return tmp_path


def test_keygen_files_and_warning(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["keygen"]) == 0
    assert "Keep it out of the agent's" in capsys.readouterr().err
    assert (tmp_path / "hakiki.key").is_file() and (tmp_path / "hakiki.pub").is_file()
    if os.name == "posix":
        assert (tmp_path / "hakiki.key").stat().st_mode & 0o777 == 0o600
    assert main(["keygen"]) == 3  # refuses to overwrite
    assert main(["keygen", "--force"]) == 0


def test_verify_exit_codes(setup, capsys):
    assert main(["verify", "run.jsonl", "--pubkey", "k.pub"]) == 0
    assert main(["checkpoint", "run.jsonl", "--key", "k.key", "--out", "cp.jsonl"]) == 0
    assert main(["verify", "run.jsonl", "--pubkey", "k.pub", "--checkpoints", "cp.jsonl"]) == 0

    lines = read_lines(setup / "run.jsonl")
    write_lines(setup / "run.jsonl", lines[:-1])
    assert main(["verify", "run.jsonl", "--pubkey", "k.pub", "--checkpoints", "cp.jsonl"]) == 2
    assert main(["checkpoint", "run.jsonl", "--key", "k.key", "--out", "cp.jsonl"]) == 0

    write_lines(setup / "run.jsonl", [lines[1], lines[0], lines[2]])
    assert main(["verify", "run.jsonl", "--pubkey", "k.pub"]) == 1
    assert main(["checkpoint", "run.jsonl", "--key", "k.key", "--out", "cp.jsonl"]) == 1
    out = capsys.readouterr().out
    assert "TAMPERED" in out and "INCOMPLETE" in out and "INTACT" in out


def test_verify_json(setup, capsys):
    import json

    capsys.readouterr()
    assert main(["verify", "run.jsonl", "--pubkey", "k.pub", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "INTACT"


def test_usage_errors(setup):
    assert main(["verify", "missing.jsonl", "--pubkey", "k.pub"]) == 3
    assert main(["verify", "run.jsonl", "--pubkey", "missing.pub"]) == 3
    assert main(["verify", "run.jsonl", "--pubkey", "run.jsonl"]) == 3  # not a key
    assert main(["verify", "run.jsonl", "--pubkey", "k.key"]) == 3  # private key given as public
    with pytest.raises(SystemExit) as info:
        main(["verify", "run.jsonl"])
    assert info.value.code == 3
    with pytest.raises(SystemExit) as info:
        main([])
    assert info.value.code == 3


def test_report_command(setup):
    assert main(["report", "run.jsonl", "--pubkey", "k.pub", "--out", "r.html"]) == 0
    assert (setup / "r.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    assert main(["report", "run.jsonl", "--pubkey", "k.pub", "--out", "r.md"]) == 0
    assert (setup / "r.md").read_text(encoding="utf-8").startswith("# Hakiki report")
    assert main(["report", "run.jsonl", "--pubkey", "k.pub", "--format", "md"]) == 0
    assert (setup / "hakiki-report.md").exists()


def test_console_entry_point(setup):
    proc = subprocess.run(
        [sys.executable, "-m", "hakiki", "verify", "run.jsonl", "--pubkey", "k.pub"],
        capture_output=True, text=True, cwd=setup,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("INTACT")
