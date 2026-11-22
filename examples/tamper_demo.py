"""Tamper demo: an edited entry is caught, and so is truncation, given a checkpoint.

    python examples/tamper_demo.py
"""

import json
import tempfile
from pathlib import Path

from hakiki import Ledger, generate_keypair, verify

workdir = Path(tempfile.mkdtemp(prefix="hakiki-tamper-"))
log, checkpoints = workdir / "run.jsonl", workdir / "checkpoints.jsonl"
private_key, public_key = generate_keypair()

ledger = Ledger(log, private_key, agent="payments-bot", model="example-model-1")


@ledger.tool(approved_by="jane@example.com")
def pay_invoice(invoice, amount):
    return "paid"


for n in range(1, 4):
    pay_invoice(f"INV-{n}", amount=100 * n)
ledger.checkpoint(checkpoints)  # in real use, send this file somewhere the operator cannot edit
pay_invoice("INV-4", amount=400)
original = log.read_bytes()


def show(title):
    result = verify(log, public_key, checkpoints)
    print(f"\n== {title}\n{result.status} (exit code {result.exit_code}): {result.explanation}")
    for problem in result.problems:
        print(f"   - {problem}")


show("1. The untouched log")

# Attack 1: edit one entry, e.g. to hide who approved a payment.
lines = original.splitlines(keepends=True)
entry = json.loads(lines[0])
entry["approval"]["by"] = "nobody"
lines[0] = (json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n").encode()
log.write_bytes(b"".join(lines))
show("2. One entry edited (approver changed to 'nobody')")

# Attack 2: delete the last entries. The remaining chain is still valid...
log.write_bytes(b"".join(original.splitlines(keepends=True)[:4]))
result = verify(log, public_key)
print(f"\n== 3. Last entries deleted, checked WITHOUT checkpoints\n{result.status}: {result.explanation}")
print("   (missed: this is why checkpoints exist)")

# ...but the checkpoint remembers how long the log was.
show("4. Same truncated log, checked WITH the checkpoint")
