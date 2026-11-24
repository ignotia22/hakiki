# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-29

First public release.

### Added

- `Ledger`: an append-only JSON Lines log where every entry is hash-chained
  with SHA-256 and signed with Ed25519. Writes are thread-safe and synced to
  disk.
- Checkpoints: signed records of a log's length and head hash, written by
  hand, by `hakiki checkpoint`, or automatically every N entries. `verify`
  reports INCOMPLETE when a log is shorter than, or differs from, a
  checkpoint.
- Built-in approvals: standing approvers (`approved_by=`), approver functions
  that block the tool unless they approve (`requires_approval=True`), and
  manual `ledger.approve(...)`.
- Private by default: arguments and results are stored as SHA-256 hashes plus
  a short summary. `capture="full"` stores raw values; `redact=[...]` drops
  named keys in either mode.
- `verify()`, which checks a log against a public key supplied by the caller
  and returns INTACT, TAMPERED or INCOMPLETE.
- Plain-English HTML and Markdown reports.
- `hakiki` CLI with `keygen`, `verify`, `checkpoint` and `report`. Exit codes:
  0 intact, 1 tampered, 2 incomplete, 3 usage error.
- `hakiki.integrations` helpers for OpenAI (Chat Completions and Responses)
  and Anthropic tool-use responses, with no SDK dependency.
- Type hints, with a `py.typed` marker.
- Examples: `quickstart.py`, `approvals.py`, `tamper_demo.py`.
- CI on Python 3.10 to 3.13 on Ubuntu, macOS and Windows.

[0.1.0]: https://github.com/ignotia22/hakiki/releases/tag/v0.1.0
