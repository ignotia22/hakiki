"""Plain-English reports (HTML or Markdown) built from a verification result."""

from __future__ import annotations

import json
from collections import Counter
from html import escape

from .verify import INCOMPLETE, INTACT, TAMPERED, VerifyResult

MAX_TIMELINE = 2000

PROVES = [
    "Every entry was signed by whoever holds the private key that matches the public key "
    "used for this check (fingerprint {key_id}).",
    "Unless the verdict says otherwise, no entry was edited, inserted, removed from the middle "
    "or reordered after it was written.",
    "If checkpoints were supplied, the log still holds everything up to the latest checkpoint.",
]
DOES_NOT_PROVE = [
    "That the agent recorded everything it did. Actions taken outside the recorded tools do "
    "not appear here.",
    "That nothing was deleted from the end of the log after the last checkpoint. Without "
    "checkpoints, entries removed from the end cannot be detected.",
    "That the holder of the private key did not rewrite the log before a checkpoint was taken. "
    "Keep the key away from the agent and keep checkpoints where the operator cannot edit them.",
    "That the times are correct. They come from the computer's own clock.",
    "Who the approvers really are. Names are recorded as the software supplied them.",
    "What the inputs and outputs were, unless full capture was switched on. By default only "
    "fingerprints (hashes) are kept, which can confirm a value you already have but not reveal it.",
]


def _when(ts) -> str:
    s = str(ts or "")
    return s[:19].replace("T", " ") + " UTC" if len(s) >= 19 else s


def _text(value, limit=200) -> str:
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _describe(e: dict) -> str:
    d = e.get("data") if isinstance(e.get("data"), dict) else {}
    a = e.get("approval") if isinstance(e.get("approval"), dict) else {}
    tool = str(d.get("tool", "?"))
    t = e.get("type")
    if t == "tool_call":
        return f"Called {tool}" + (f", approved by {a.get('by')}" if a.get("by") else "")
    if t == "tool_result":
        return f"{tool} finished" + (f" in {d['ms']} ms" if "ms" in d else "")
    if t == "tool_error":
        return f"{tool} failed with {d.get('error', 'an error')}"
    if t == "approval":
        what = d.get("action") or tool
        who = a.get("by") or "No one"
        out = f"{who} {a.get('status', 'decided on')} {what}"
        return out + (f": {a['reason']}" if a.get("reason") else "")
    if t == "note":
        return "Note: " + _text(d.get("message", ""))
    if t == "checkpoint":
        return f"Checkpoint taken at entry {int(d.get('seq', -1)) + 1}"
    return _text(d)


def build_report(result: VerifyResult) -> dict:
    """Collect everything a report shows into a plain dictionary."""
    entries = result.entries
    tools: dict = {}
    approvals = []
    blocked = Counter()
    for e in entries:
        d = e.get("data") if isinstance(e.get("data"), dict) else {}
        a = e.get("approval") if isinstance(e.get("approval"), dict) else {}
        tool = str(d.get("tool", "?"))
        t = e.get("type")
        if t in ("tool_call", "tool_result", "tool_error"):
            row = tools.setdefault(tool, {"calls": 0, "succeeded": 0, "failed": 0, "blocked": 0})
            row[{"tool_call": "calls", "tool_result": "succeeded", "tool_error": "failed"}[t]] += 1
        if t == "approval":
            if a.get("status") == "rejected" and "tool" in d:
                tools.setdefault(tool, {"calls": 0, "succeeded": 0, "failed": 0, "blocked": 0})
                tools[tool]["blocked"] += 1
            approvals.append({
                "when": _when(e.get("ts")),
                "what": str(d.get("action") or tool),
                "decision": str(a.get("status", "?")),
                "by": str(a.get("by") or "—"),
                "reason": str(a.get("reason") or ""),
            })
        elif t == "tool_call" and a.get("standing"):
            approvals.append({
                "when": _when(e.get("ts")), "what": tool, "decision": "approved (standing)",
                "by": str(a.get("by")), "reason": "",
            })

    def distinct(field):
        return ", ".join(sorted({str(e.get(field)) for e in entries if e.get(field)})) or "—"

    return {
        "verdict": result.status,
        "explanation": result.explanation,
        "problems": result.problems,
        "overview": [
            ("Agent", distinct("agent")),
            ("Model", distinct("model")),
            ("Run by", distinct("actor")),
            ("First entry", _when(entries[0].get("ts")) if entries else "—"),
            ("Last entry", _when(entries[-1].get("ts")) if entries else "—"),
            ("Entries", str(len(entries))),
            ("Checkpoints matched", str(result.checkpoints_checked)),
            ("Log ID", distinct("log_id")),
            ("Key fingerprint", result.key_id),
        ],
        "tools": sorted(tools.items()),
        "approvals": approvals,
        "timeline": [
            (str(e.get("seq", "?") + 1 if isinstance(e.get("seq"), int) else "?"),
             _when(e.get("ts")), str(e.get("type", "?")).replace("_", " "), _describe(e))
            for e in entries[:MAX_TIMELINE]
        ],
        "timeline_truncated": max(0, len(entries) - MAX_TIMELINE),
        "proves": [p.format(key_id=result.key_id) for p in PROVES],
        "does_not_prove": DOES_NOT_PROVE,
    }


# -- Markdown ------------------------------------------------------------


def _md_cell(s) -> str:
    s = str(s).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def render_markdown(result: VerifyResult) -> str:
    r = build_report(result)
    parts = ["# Hakiki report", f"## Verdict: {r['verdict']}", _md_cell(r["explanation"])]
    if r["problems"]:
        parts.append("**Problems found:**\n\n" + "\n".join(f"- {_md_cell(p)}" for p in r["problems"][:50]))
    parts += ["## Overview", _md_table(["", ""], r["overview"])]
    parts.append("## What the agent did")
    parts.append(
        _md_table(["Tool", "Calls", "Succeeded", "Failed", "Blocked"],
                  [(n, c["calls"], c["succeeded"], c["failed"], c["blocked"]) for n, c in r["tools"]])
        if r["tools"] else "No tool calls were recorded."
    )
    parts.append("## Approvals")
    parts.append(
        _md_table(["When", "Action", "Decision", "By", "Reason"],
                  [(a["when"], a["what"], a["decision"], a["by"], a["reason"]) for a in r["approvals"]])
        if r["approvals"] else "No approvals were recorded."
    )
    parts += ["## Timeline", _md_table(["#", "When", "Type", "What happened"], r["timeline"])]
    if r["timeline_truncated"]:
        parts.append(f"_{r['timeline_truncated']} later entries are not shown._")
    parts += [
        "## What this report does and doesn't prove",
        "**It shows:**\n\n" + "\n".join(f"- {_md_cell(p)}" for p in r["proves"]),
        "**It does not show:**\n\n" + "\n".join(f"- {_md_cell(p)}" for p in r["does_not_prove"]),
    ]
    return "\n\n".join(parts) + "\n"


# -- HTML ----------------------------------------------------------------

_CSS = """
body{font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#1f2328;
background:#fff;max-width:960px;margin:0 auto;padding:24px 16px}
h1{font-size:1.1rem;color:#57606a;margin:0 0 12px;font-weight:600}
h2{font-size:1.25rem;margin:32px 0 8px;border-bottom:1px solid #d0d7de;padding-bottom:4px}
.verdict{border-radius:8px;padding:20px 24px;border:2px solid}
.verdict strong{display:block;font-size:2.6rem;letter-spacing:.04em;line-height:1.1}
.verdict p{margin:8px 0 0;font-size:1.1rem}
.INTACT{background:#dafbe1;border-color:#1a7f37;color:#0f5323}
.TAMPERED{background:#ffebe9;border-color:#cf222e;color:#82071e}
.INCOMPLETE{background:#fff8c5;border-color:#9a6700;color:#6b4700}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #d0d7de;vertical-align:top}
th{background:#f6f8fa}
.n{text-align:right;font-variant-numeric:tabular-nums}
.overview th{width:30%;background:none;font-weight:600}
.wrap{overflow-x:auto}
code,.mono{font-family:ui-monospace,Consolas,monospace;font-size:.85em;word-break:break-all}
.rejected{color:#cf222e;font-weight:600}
.muted{color:#57606a}
ul{padding-left:20px}
@media print{body{padding:0;max-width:none}.verdict{-webkit-print-color-adjust:exact;
print-color-adjust:exact}tr{break-inside:avoid}h2{break-after:avoid}}
"""


def _table(headers, rows, numeric=()) -> str:
    head = "".join(
        f'<th class="n">{escape(h)}</th>' if i in numeric else f"<th>{escape(h)}</th>"
        for i, h in enumerate(headers)
    )
    body = "".join(
        "<tr>" + "".join(
            f'<td class="n">{escape(str(c))}</td>' if i in numeric else f"<td>{c}</td>"
            for i, c in enumerate(row)
        ) + "</tr>"
        for row in rows
    )
    return f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render_html(result: VerifyResult) -> str:
    r = build_report(result)
    e = escape
    out = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>Hakiki report: {e(r['verdict'])}</title><style>{_CSS}</style></head><body>",
        "<h1>Hakiki report</h1>",
        f'<div class="verdict {e(r["verdict"])}"><strong>{e(r["verdict"])}</strong>'
        f"<p>{e(r['explanation'])}</p></div>",
    ]
    if r["problems"]:
        items = "".join(f"<li>{e(p)}</li>" for p in r["problems"][:50])
        more = len(r["problems"]) - 50
        out.append(f"<h2>Problems found</h2><ul>{items}</ul>")
        if more > 0:
            out.append(f'<p class="muted">…and {more} more.</p>')
    out.append('<h2>Overview</h2><div class="wrap"><table class="overview"><tbody>')
    out += [
        f"<tr><th>{e(k)}</th><td{' class=mono' if k in ('Log ID', 'Key fingerprint') else ''}>{e(v)}</td></tr>"
        for k, v in r["overview"]
    ]
    out.append("</tbody></table></div><h2>What the agent did</h2>")
    if r["tools"]:
        rows = [(e(n), c["calls"], c["succeeded"], c["failed"], c["blocked"]) for n, c in r["tools"]]
        out.append(_table(["Tool", "Calls", "Succeeded", "Failed", "Blocked"], rows, numeric=(1, 2, 3, 4)))
    else:
        out.append("<p>No tool calls were recorded.</p>")
    out.append("<h2>Approvals</h2>")
    if r["approvals"]:
        rows = [
            (e(a["when"]), e(a["what"]),
             f'<span class="rejected">{e(a["decision"])}</span>' if a["decision"] == "rejected" else e(a["decision"]),
             e(a["by"]), e(a["reason"]))
            for a in r["approvals"]
        ]
        out.append(_table(["When", "Action", "Decision", "By", "Reason"], rows))
    else:
        out.append("<p>No approvals were recorded.</p>")
    out.append("<h2>Timeline</h2>")
    if result.status != INTACT:
        out.append('<p class="muted">Entries are shown as they appear in the file and may not be trustworthy.</p>')
    out.append(_table(["#", "When", "Type", "What happened"],
                      [tuple(e(c) for c in row) for row in r["timeline"]], numeric=()))
    if r["timeline_truncated"]:
        out.append(f'<p class="muted">{r["timeline_truncated"]} later entries are not shown.</p>')
    out.append("<h2>What this report does and doesn't prove</h2><p><strong>It shows:</strong></p><ul>")
    out += [f"<li>{e(p)}</li>" for p in r["proves"]]
    out.append("</ul><p><strong>It does not show:</strong></p><ul>")
    out += [f"<li>{e(p)}</li>" for p in r["does_not_prove"]]
    out.append("</ul></body></html>\n")
    return "".join(out)


def render(result: VerifyResult, fmt: str = "html") -> str:
    if fmt == "html":
        return render_html(result)
    if fmt in ("md", "markdown"):
        return render_markdown(result)
    raise ValueError('format must be "html" or "md"')


__all__ = ["build_report", "render", "render_html", "render_markdown", "INTACT", "TAMPERED", "INCOMPLETE"]
