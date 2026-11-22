"""Command line: hakiki keygen | verify | checkpoint | report.

Exit codes: 0 intact, 1 tampered, 2 incomplete, 3 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .checkpoint import append_checkpoint, make_checkpoint
from .keys import generate_keypair, load_private_key, load_public_key, save_private_key, save_public_key
from .report import render
from .verify import INTACT, verify

EXIT_USAGE = 3

KEY_WARNING = """\
Anyone holding {key} can sign log entries. Keep it out of the agent's
reach: not in its working directory, prompts, tools or environment dumps.
Load it only into the Ledger, ideally from a secrets manager, and give
{pub} to the people who will verify the log."""


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="hakiki", description="Hakiki: the tech log for AI agents.")
    p.add_argument("--version", action="version", version=f"hakiki {__version__}")
    sub = p.add_subparsers(dest="command", required=True, parser_class=_Parser)

    k = sub.add_parser("keygen", help="create a signing key pair")
    k.add_argument("--out", default="hakiki", help="file name prefix (default: hakiki)")
    k.add_argument("--force", action="store_true", help="overwrite existing key files")

    v = sub.add_parser("verify", help="check a log against a public key")
    v.add_argument("log")
    v.add_argument("--pubkey", required=True)
    v.add_argument("--checkpoints")
    v.add_argument("--json", action="store_true", help="print the result as JSON")

    c = sub.add_parser("checkpoint", help="record a signed checkpoint of a log's current end")
    c.add_argument("log")
    c.add_argument("--key", required=True, help="private key that signed the log")
    c.add_argument("--out", required=True, help="checkpoints file to append to")

    r = sub.add_parser("report", help="write a plain-English report")
    r.add_argument("log")
    r.add_argument("--pubkey", required=True)
    r.add_argument("--checkpoints")
    r.add_argument("--format", choices=["html", "md"])
    r.add_argument("--out", help="output file (default: hakiki-report.html or .md)")
    return p


def _need_file(path):
    if path is not None and not Path(path).is_file():
        raise UsageError(f"file not found: {path}")


def _load(loader, path):
    _need_file(path)
    try:
        return loader(path)
    except (ValueError, TypeError) as exc:
        raise UsageError(f"cannot read key {path}: {exc}") from exc


def cmd_keygen(args) -> int:
    key_path, pub_path = Path(args.out + ".key"), Path(args.out + ".pub")
    if not args.force:
        for path in (key_path, pub_path):
            if path.exists():
                raise UsageError(f"{path} already exists (use --force to overwrite)")
    private_key, public_key = generate_keypair()
    save_private_key(private_key, key_path, overwrite=True)
    save_public_key(public_key, pub_path, overwrite=True)
    print(f"Wrote private key {key_path} and public key {pub_path}")
    print("WARNING: " + KEY_WARNING.format(key=key_path, pub=pub_path), file=sys.stderr)
    return 0


def _print_result(result, as_json=False):
    if as_json:
        print(json.dumps({
            "status": result.status,
            "explanation": result.explanation,
            "entries": len(result.entries),
            "checkpoints_checked": result.checkpoints_checked,
            "problems": result.problems,
        }, indent=2))
        return
    print(f"{result.status}: {result.explanation}")
    for problem in result.problems[:20]:
        print(f"  - {problem}")
    if len(result.problems) > 20:
        print(f"  ...and {len(result.problems) - 20} more")


def cmd_verify(args) -> int:
    _need_file(args.log)
    _need_file(args.checkpoints)
    pub = _load(load_public_key, args.pubkey)
    result = verify(args.log, pub, args.checkpoints)
    _print_result(result, args.json)
    return result.exit_code


def cmd_checkpoint(args) -> int:
    _need_file(args.log)
    key = _load(load_private_key, args.key)
    result = verify(args.log, key.public_key())
    if result.status != INTACT:
        print("Refusing to checkpoint a log that does not verify.", file=sys.stderr)
        _print_result(result)
        return result.exit_code
    head = result.entries[-1]
    cp = make_checkpoint(head["log_id"], head["seq"], head["hash"], key)
    append_checkpoint(cp, args.out)
    print(f"Checkpoint written to {args.out}: {cp['count']} entries, head {cp['head_hash'][:16]}…")
    print("Store this file where the agent's operator cannot edit it.", file=sys.stderr)
    return 0


def cmd_report(args) -> int:
    _need_file(args.log)
    _need_file(args.checkpoints)
    pub = _load(load_public_key, args.pubkey)
    fmt = args.format or ("md" if args.out and args.out.endswith(".md") else "html")
    out = Path(args.out or f"hakiki-report.{fmt}")
    result = verify(args.log, pub, args.checkpoints)
    out.write_text(render(result, fmt), encoding="utf-8")
    print(f"{result.status}: report written to {out}")
    return result.exit_code


COMMANDS = {"keygen": cmd_keygen, "verify": cmd_verify, "checkpoint": cmd_checkpoint, "report": cmd_report}


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except UsageError as exc:
        print(f"hakiki: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"hakiki: error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
