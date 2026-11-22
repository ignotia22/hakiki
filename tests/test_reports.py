import pytest
from conftest import dump, load, read_lines, write_lines

from hakiki import Approval, ApprovalRejected, Ledger, verify
from hakiki.report import build_report, render, render_html, render_markdown


@pytest.fixture
def busy_log(keys, log_path):
    ledger = Ledger(log_path, keys[0], agent="invoice-bot", model="model-x", actor="ops")

    @ledger.tool(approved_by="jane@example.com")
    def send_invoice(n):
        return n

    @ledger.tool(requires_approval=True, approver=lambda t, a: Approval("rejected", "sam@example.com", "<b>too big</b>"))
    def refund(amount):
        pass

    @ledger.tool
    def lookup(x):
        raise KeyError(x)

    send_invoice(1)
    send_invoice(2)
    with pytest.raises(ApprovalRejected):
        refund(900)
    with pytest.raises(KeyError):
        lookup("acct")
    ledger.approve("close ticket 7", by="jane@example.com", reason="customer confirmed")
    ledger.note("run | finished")
    return log_path


def test_report_model(busy_log, keys):
    r = build_report(verify(busy_log, keys[1]))
    assert r["verdict"] == "INTACT"
    tools = dict(r["tools"])
    assert tools["send_invoice"] == {"calls": 2, "succeeded": 2, "failed": 0, "blocked": 0}
    assert tools["refund"]["blocked"] == 1
    assert tools["lookup"]["failed"] == 1
    decisions = [(a["what"], a["decision"], a["by"]) for a in r["approvals"]]
    assert ("refund", "rejected", "sam@example.com") in decisions
    assert ("close ticket 7", "approved", "jane@example.com") in decisions
    assert decisions.count(("send_invoice", "approved (standing)", "jane@example.com")) == 2


def test_html_report(busy_log, keys):
    html = render_html(verify(busy_log, keys[1]))
    assert html.startswith("<!doctype html>")
    assert "<script" not in html.lower()  # no JavaScript, and user text is escaped
    assert "&lt;b&gt;too big&lt;/b&gt;" in html
    assert 'class="verdict INTACT"' in html
    assert "@media print" in html
    for heading in ("What the agent did", "Approvals", "Timeline", "does and doesn't prove"):
        assert heading in html
    assert html.index("INTACT") < html.index("What the agent did") < html.index("Approvals") < html.index("Timeline")


def test_markdown_report(busy_log, keys):
    md = render_markdown(verify(busy_log, keys[1]))
    assert md.startswith("# Hakiki report")
    assert "## Verdict: INTACT" in md
    assert "| send_invoice | 2 | 2 | 0 | 0 |" in md
    assert "run \\| finished" in md
    assert "&lt;b&gt;" in md


def test_report_on_tampered_log(busy_log, keys):
    lines = read_lines(busy_log)
    e = load(lines[0])
    e["data"]["tool"] = "nothing_to_see"
    lines[0] = dump(e)
    write_lines(busy_log, lines)
    result = verify(busy_log, keys[1])
    html = render(result, "html")
    assert 'class="verdict TAMPERED"' in html
    assert "Problems found" in html
    assert "may not be trustworthy" in html
    assert "## Verdict: TAMPERED" in render(result, "md")


def test_report_survives_mangled_entries(keys, log_path):
    log_path.write_text('{"seq": "x", "data": [1, 2], "approval": "yes", "type": "approval"}\n')
    result = verify(log_path, keys[1])
    assert result.status == "TAMPERED"
    assert "TAMPERED" in render(result, "html")
    assert "TAMPERED" in render(result, "md")


def test_unknown_format(busy_log, keys):
    with pytest.raises(ValueError):
        render(verify(busy_log, keys[1]), "pdf")
