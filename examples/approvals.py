"""Approvals: standing approvals, approver functions, and manual sign-off.

    python examples/approvals.py
"""

import tempfile
from pathlib import Path

from hakiki import Approval, ApprovalRejected, Ledger, generate_keypair, verify
from hakiki.report import render

workdir = Path(tempfile.mkdtemp(prefix="hakiki-approvals-"))
private_key, public_key = generate_keypair()
ledger = Ledger(workdir / "run.jsonl", private_key, agent="refund-bot", model="example-model-1", actor="support-team")


# 1. A standing approval: this tool is pre-approved by a named person.
@ledger.tool(approved_by="jane@example.com")
def send_receipt(order_id):
    return "sent"


# 2. An approver function decides before each call. Anything other than an
#    "approved" decision blocks the tool and raises ApprovalRejected.
def refund_policy(tool_name, args):
    if args["amount"] <= 100:
        return Approval("approved", by="refund-policy-v2", reason="under the 100 limit")
    return Approval("rejected", by="refund-policy-v2", reason="over the 100 limit; needs a manager")


@ledger.tool(requires_approval=True, approver=refund_policy)
def issue_refund(order_id, amount):
    return f"refunded {amount} on {order_id}"


send_receipt("A-1001")
print(issue_refund("A-1001", amount=40))
try:
    issue_refund("A-1002", amount=950)
except ApprovalRejected as exc:
    print(f"Blocked: {exc}")

# 3. A human decision made outside the agent, recorded in the same log.
ledger.approve("refund 950 on A-1002", by="manager@example.com", reason="long-standing customer")

result = verify(workdir / "run.jsonl", public_key)
print()
print(render(result, "md").split("## Timeline")[0])
