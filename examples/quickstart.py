"""Quickstart: record an agent's tool calls, verify the log, write a report.

    pip install -e .
    python examples/quickstart.py
"""

import tempfile
from pathlib import Path

from hakiki import Ledger, generate_keypair, verify
from hakiki.report import render

workdir = Path(tempfile.mkdtemp(prefix="hakiki-quickstart-"))
private_key, public_key = generate_keypair()  # in real use: `hakiki keygen`, then load the key

# The two lines you add to an agent: create a ledger, decorate the tools.
ledger = Ledger(workdir / "run.jsonl", private_key, agent="support-bot", model="example-model-1")


@ledger.tool
def lookup_order(order_id):
    return {"order_id": order_id, "status": "shipped"}


@ledger.tool
def send_email(to, body):
    return "sent"


# The agent runs as normal.
order = lookup_order("A-1001")
send_email("customer@example.com", f"Your order is {order['status']}.")
ledger.note("conversation closed")

# Anyone with the public key can check the log later.
result = verify(workdir / "run.jsonl", public_key)
print(f"{result.status}: {result.explanation}")

report = workdir / "report.html"
report.write_text(render(result, "html"), encoding="utf-8")
print(f"Log:    {workdir / 'run.jsonl'}")
print(f"Report: {report}")
