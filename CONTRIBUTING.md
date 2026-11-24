# Contributing

Thanks for helping. Hakiki stays useful by staying small, so a few rules apply.

## Run the tests

```bash
git clone https://github.com/ignotia22/hakiki
cd hakiki
python -m pip install -e ".[test]"
python -m pytest
```

CI runs the suite on Python 3.10 to 3.13 on Linux, macOS and Windows. Please run it locally before opening a pull request.

## Ground rules

- **One runtime dependency.** `cryptography` is the only one. A change that needs another dependency needs a very good reason, so discuss it in an issue first.
- **Keep the core small.** The package is about 1,300 lines and should stay readable in an evening. Check with `wc -l src/hakiki/*.py`.
- **Attack your change.** If it touches the log format, verification or checkpoints, add a test that tries to break it.
- **Keep the log format stable.** Logs written by one version must verify with the next. Format changes need a new `v` value and a migration plan.
- **Open an issue before large changes**, such as new features, new integrations or anything that changes the public API. A short discussion saves wasted work on both sides.

## Security issues

Please do not report vulnerabilities in public issues. See [SECURITY.md](SECURITY.md).
