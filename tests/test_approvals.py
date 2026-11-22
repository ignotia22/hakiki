import pytest

from hakiki import Approval, ApprovalRejected, INTACT, Ledger, verify


def entries(log_path, keys):
    result = verify(log_path, keys[1])
    assert result.status == INTACT
    return result.entries


def test_fixed_approver_is_recorded(keys, log_path):
    ledger = Ledger(log_path, keys[0])

    @ledger.tool(approved_by="jane@example.com")
    def send_invoice(n):
        return n

    send_invoice(7)
    call = entries(log_path, keys)[0]
    assert call["type"] == "tool_call"
    assert call["approval"] == {"status": "approved", "by": "jane@example.com", "standing": True}


def test_approval_lets_the_tool_run(keys, log_path):
    ledger = Ledger(log_path, keys[0])
    seen = []

    def approver(tool, args):
        seen.append((tool, args))
        return Approval("approved", by="jane@example.com", reason="within budget")

    @ledger.tool(requires_approval=True, approver=approver)
    def pay(amount):
        return f"paid {amount}"

    assert pay(40) == "paid 40"
    assert seen == [("pay", {"amount": 40})]
    log = entries(log_path, keys)
    assert [e["type"] for e in log] == ["approval", "tool_call", "tool_result"]
    assert log[0]["approval"] == {"status": "approved", "by": "jane@example.com", "reason": "within budget"}
    assert log[1]["approval"]["ref_seq"] == 0


@pytest.mark.parametrize(
    "decision",
    [
        Approval("rejected", by="jane@example.com", reason="too large"),
        None,  # approver gave no answer
        True,  # not an Approval
    ],
)
def test_rejection_blocks_the_tool_and_is_recorded(keys, log_path, decision):
    ledger = Ledger(log_path, keys[0])
    ran = []

    @ledger.tool(requires_approval=True, approver=lambda tool, args: decision)
    def pay(amount):
        ran.append(amount)

    with pytest.raises(ApprovalRejected) as info:
        pay(10_000)
    assert ran == []
    assert info.value.tool == "pay"
    log = entries(log_path, keys)
    assert [e["type"] for e in log] == ["approval"]
    assert log[0]["approval"]["status"] == "rejected"
    if isinstance(decision, Approval):
        assert log[0]["approval"]["by"] == "jane@example.com"
        assert log[0]["approval"]["reason"] == "too large"


def test_crashing_approver_blocks_the_tool(keys, log_path):
    ledger = Ledger(log_path, keys[0])

    def approver(tool, args):
        raise ConnectionError("approval service down")

    @ledger.tool(requires_approval=True, approver=approver)
    def delete_everything():
        raise AssertionError("must not run")

    with pytest.raises(ApprovalRejected):
        delete_everything()
    log = entries(log_path, keys)
    assert log[0]["approval"]["reason"] == "approver raised ConnectionError"


def test_manual_approval(keys, log_path):
    ledger = Ledger(log_path, keys[0])
    ledger.approve("release refund #42", by="sam@example.com", reason="checked receipt")
    ledger.approve("delete account", by="sam@example.com", status="rejected")
    log = entries(log_path, keys)
    assert log[0]["data"] == {"action": "release refund #42"}
    assert log[0]["approval"]["status"] == "approved"
    assert log[1]["approval"]["status"] == "rejected"


def test_bad_options(keys, log_path):
    ledger = Ledger(log_path, keys[0])
    with pytest.raises(ValueError):
        Approval("maybe")
    with pytest.raises(ValueError):
        ledger.tool(requires_approval=True)
    with pytest.raises(ValueError):
        ledger.tool(requires_approval=True, approver=lambda t, a: None, approved_by="x")
