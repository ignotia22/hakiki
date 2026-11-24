# Security policy

Hakiki exists to make tampering visible, so a flaw that hides tampering is the most serious kind of bug it can have.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's private vulnerability reporting:

1. Go to the [Security tab](https://github.com/ignotia22/hakiki/security) of this repository.
2. Choose **Report a vulnerability**.
3. Describe the problem and include a log, key pair and command that reproduce it, if you can.

Please do not open a public issue for a vulnerability.

## In scope

Anything that lets a changed log verify as INTACT, or a shortened log pass a checkpoint check. For example:

- an edited, inserted, removed or reordered entry that `verify` accepts
- an entry or checkpoint accepted with a forged or mismatched signature
- a way to make `verify` trust a key other than the one the caller passes
- raw argument or result values written to the log in the default `capture="hash"` mode
- a report that shows a verdict different from the one `verify` returns

## Out of scope

The limitations listed in the README are known and documented. That includes truncation with no checkpoint, and rewrites by someone who holds the private key back to the latest checkpoint they cannot reach. Reports that show a new way around them are still welcome.

## Supported versions

Fixes go into the latest released version. Older versions do not receive patches, so please upgrade.
