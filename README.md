# Hakiki

**The tech log for AI agents.**

*Hakiki* (said ha-KEE-kee) is Swahili for "verify". It records what an AI agent did, which model it ran on and who approved each action, in a signed log that nobody can quietly edit or trim afterwards.

```text
INTACT       every entry is genuine and in order
TAMPERED     something was edited, added, removed or reordered
INCOMPLETE   entries are missing compared with a checkpoint
```

## 60-second quickstart

```bash
pip install git+https://github.com/ignotia22/hakiki
hakiki keygen                      # writes hakiki.key (private) and hakiki.pub (public)
```

Add two things to your agent: a ledger, and a decorator on each tool.

```python
from hakiki import Ledger

ledger = Ledger("run.jsonl", key="hakiki.key", agent="support-bot", model="example-model-1",
                checkpoint_every=50, checkpoint_path="checkpoints.jsonl")

@ledger.tool
def lookup_order(order_id):
    return {"order_id": order_id, "status": "shipped"}

@ledger.tool(approved_by="jane@example.com")
def send_email(to, body):
    ...
```

Then anyone with the public key can check the log and produce a report:

```bash
hakiki verify run.jsonl --pubkey hakiki.pub --checkpoints checkpoints.jsonl
hakiki report run.jsonl --pubkey hakiki.pub --checkpoints checkpoints.jsonl --format html --out report.html
```

`verify` exits with `0` intact, `1` tampered, `2` incomplete or `3` usage error, so it works in scripts and CI.

The `examples/` folder has three runnable scripts: `quickstart.py`, `approvals.py` and `tamper_demo.py`.

## Why

AI agents now send emails, move money and change records. When something goes wrong, or when a client, insurer or auditor asks what happened, ordinary application logs are not good enough evidence. Anyone with access to the server can edit them, and nobody can tell.

Hakiki gives an agent a tech log in the aviation sense: a running record of every action, signed as it is written, that shows clearly if anyone changes it later. It is deliberately small:

- **One dependency** (`cryptography`) and about 1,300 lines of code. No daemon, proxy, server or Docker. Works on Windows, macOS and Linux.
- **Catches deleted entries at the end of the log**, not just edits, by using checkpoints.
- **Approvals are part of the log**. A tool can refuse to run until someone approves it, and the decision is recorded alongside the action.
- **Private by default**. It stores fingerprints (hashes) of arguments and results, not the data itself.
- **A report a non-engineer can read**, with a clear verdict at the top.

## How it works

**Entries.** The log is a JSON Lines file with one entry per event. The types are `tool_call`, `tool_result`, `tool_error`, `approval`, `note` and `checkpoint`. Each entry looks like this:

```json
{"v":1,"seq":0,"ts":"2026-11-22T09:14:03.120391Z","log_id":"6f1c…","prev_hash":"0000…0000",
 "agent":"support-bot","model":"example-model-1","actor":"ops","type":"tool_call",
 "data":{"tool":"lookup_order","args":{"sha256":"43258c…","summary":{"type":"dict","len":1,"keys":["order_id"]}}},
 "key_id":"8989bb6dba1d2f81","hash":"b83166…","sig":"978bc9…"}
```

**Hash chain.** `hash` is SHA-256 over the entry's canonical JSON (sorted keys, compact separators, UTF-8), leaving out `hash` and `sig`. Each entry's `prev_hash` is the previous entry's `hash`, and the first entry uses 64 zeros. Changing, inserting, removing or reordering any entry breaks the chain.

**Signatures.** `sig` is an Ed25519 signature over `hash`. `key_id` is a short fingerprint of the public key, for display only. `verify` always checks against the public key you pass it and never trusts a key stored in the log.

**Writing.** Appends are protected by a lock, so threads can share one ledger. Each entry is flushed and synced to disk before the call returns. If you reopen an existing log, the ledger continues its chain.

**Approvals.** There are three ways to record approval:

```python
from hakiki import Approval, ApprovalRejected

@ledger.tool(approved_by="jane@example.com")            # 1. standing approval, recorded on every call
def send_receipt(order_id): ...

def refund_policy(tool_name, args):                     # 2. decided before each call
    if args["amount"] <= 100:
        return Approval("approved", by="refund-policy", reason="under limit")
    return Approval("rejected", by="refund-policy", reason="needs a manager")

@ledger.tool(requires_approval=True, approver=refund_policy)
def issue_refund(order_id, amount): ...

ledger.approve("refund 950 on A-1002", by="manager@example.com")   # 3. recorded by hand
```

With `requires_approval=True`, the tool runs only if the approver returns `Approval("approved", ...)`. A rejection, no answer, any other return value, or an approver that crashes all count as "no". In each of those cases the decision is recorded, the tool does not run, and `ApprovalRejected` is raised. Blocking is the safe default.

**Privacy.** With the default `capture="hash"`, the log stores the SHA-256 of each argument set and result, plus a short summary: type, length and top-level keys. Raw values never reach the file, and a test checks this. `capture="full"` stores raw values. `redact=["password", "api_key"]` drops those keys at any depth in either mode, before anything is hashed or stored.

**Checkpoints.** A checkpoint is a small signed record of how far the log had reached: `log_id`, `seq`, `head_hash`, `count` and `ts`. There's more on these below.

**Integrations.** You can pass a model's response straight to a helper, which records each tool call and runs it. The OpenAI and Anthropic SDKs are not dependencies, and plain dicts work too.

```python
from hakiki.integrations import run_openai_tool_calls, run_anthropic_tool_uses

tool_messages = run_openai_tool_calls(ledger, response, {"lookup_order": lookup_order})
tool_results  = run_anthropic_tool_uses(ledger, response, {"lookup_order": lookup_order})
```

Errors and rejections are recorded and returned to the model as error results, so your agent loop keeps going.

**Python API.** The main names are `Ledger`, `Approval`, `ApprovalRejected`, `generate_keypair` and `verify`. `verify(log, public_key, checkpoints=None)` returns a result with `.status`, `.explanation`, `.problems` and `.exit_code`. `hakiki.report.render(result, "html" | "md")` builds a report.

## Who it's for

- **Business owners** get a plain-English report to hand to a client, insurer or auditor. It opens with a large verdict (INTACT, TAMPERED or INCOMPLETE) and a one-sentence explanation. Then it shows what the agent did as counts by tool, a table of who approved or rejected what and when, and a timeline. It ends with an honest section on what the report does and doesn't prove. The HTML is a single file that works without JavaScript and prints cleanly.
- **AI agent builders** add two lines: create a `Ledger`, then decorate your tools. There's no service to run and nothing to deploy.
- **Software engineers** can read the whole thing in an evening. It uses SHA-256, Ed25519 and canonical JSON. The test suite attacks the log with edits, deletions, reordering, insertions, forged signatures, wrong keys, truncation and tampered checkpoints, and it states plainly which attacks it can't catch.

## Checkpoints and where to keep them

A hash chain catches changes *inside* the log. On its own, it can't tell if someone simply deletes the last few entries, because what remains is still a perfectly valid chain. The test suite demonstrates this gap (`test_truncation_without_checkpoint_is_missed`).

Checkpoints close that gap. Each one records how long the log was and the hash of its last entry at that moment. If the log later turns out to be shorter, or the entry at that position differs, `verify` reports **INCOMPLETE**.

```bash
hakiki checkpoint run.jsonl --key hakiki.key --out checkpoints.jsonl   # by hand or on a schedule
```

You can also have the ledger write checkpoints automatically: `Ledger(..., checkpoint_every=50, checkpoint_path="checkpoints.jsonl")`.

**Checkpoints only protect you if they are stored where the agent's operator cannot edit them.** A checkpoint file that sits next to the log, on the same machine, can be trimmed along with it. Copy checkpoints somewhere else as they are made, for example:

- email them to the client;
- commit them to a separate repository the operator cannot rewrite;
- copy them to separate storage with versioning or write-once retention.

The log's protection runs up to the latest checkpoint held somewhere safe. Entries written after that checkpoint can still be dropped without detection.

## Limitations

Hakiki is evidence that a log was not changed after it was written. It is not proof that the log is complete or true. In particular:

- **No checkpoints, no truncation detection.** Without checkpoints kept out of the operator's reach, deleting entries from the end of the log goes undetected.
- **The key holder can rewrite history.** The ledger needs the private key to sign, so it lives in the agent's process. Whoever controls that machine and key can forge new entries, or rewrite the whole log as far back as the latest checkpoint they cannot reach. Keep the key out of the agent's own reach (its working directory, prompts and tools), and keep checkpoints elsewhere.
- **It only sees what it wraps.** Actions taken outside `@ledger.tool`, `ledger.call` or the integrations are not recorded.
- **Timestamps come from the local clock** and are not independently certified.
- **Hashes are not encryption.** A hash of a low-variety value, such as "yes", a small amount or an email address from a known list, can be guessed by trying candidates. Summaries also reveal types, lengths and top-level dictionary keys. Redacted keys are dropped before hashing, so the hash does not cover them.
- **Notes, approver names and approval reasons are stored as written**, and approvers are not authenticated. Hakiki records the name your code supplies.
- **One writer process per log file.** Writes are thread-safe, but two processes appending to the same file are not supported. Use one log per process.
- **Async tools are not supported** in v0.1. Decorating one raises `TypeError`.
- Values that aren't JSON are captured using `repr()`, so their hashes may not be reproducible elsewhere.
- If the process crashes mid-write and leaves a partial last line, `verify` reports TAMPERED and the ledger refuses to append to the file.

## When Hakiki isn't the right tool

Hakiki is a tamper-evident record, and nothing more. If you need to replay agent runs, diff behaviour between versions, enforce policies through a proxy, or browse traces in a dashboard, use a fuller observability or governance platform. You can still run Hakiki alongside it if you want a signed record that a third party can check independently.

## Roadmap

- RFC 3161 trusted timestamps for entries and checkpoints
- Adapters for LangChain, CrewAI and MCP
- EU AI Act and ISO 42001 mapping in reports
- A hosted checkpoint service, so checkpoints are stored out of the operator's reach by default

---

Licensed under the [Apache License 2.0](LICENSE).
