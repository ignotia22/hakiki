import os
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.mark.parametrize("name", ["quickstart.py", "approvals.py", "tamper_demo.py"])
def test_example_runs(name):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / name)], capture_output=True, text=True, encoding="utf-8", env=env
    )
    assert proc.returncode == 0, proc.stderr
    if name == "tamper_demo.py":
        out = proc.stdout
        assert out.count("TAMPERED") >= 1 and "INCOMPLETE" in out
