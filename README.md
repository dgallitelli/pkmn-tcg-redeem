# Gotta Redeem 'Em All - Pokemon TCG Live Booster Code Auto-Redeemer

![Gotta Redeem 'Em All banner](docs/images/banner.png)

**pkmn-tcg-redeem** — redeems Pokémon TCG Live booster codes in batch, from the command line, against your own account.

## Why this exists

`redeem.tcg.pokemon.com` has no official API and is protected by invisible, score-based reCAPTCHA
Enterprise. Automating it from a cloud/datacenter browser gets silently blocked; automating it from
a real local Chrome on a residential IP works.

## Requirements

- macOS with Google Chrome installed at `/Applications/Google Chrome.app` (the tool drives your real
  Chrome over CDP, not Playwright's bundled Chromium -- so no `playwright install` step is needed).
- Python 3.10+ (developed and verified on 3.14).

## Setup

Run all commands from the repo root.

1. `python3 -m venv /tmp/venvs/pkmn-tcg-redeem/.venv`
2. `/tmp/venvs/pkmn-tcg-redeem/.venv/bin/pip install -r requirements.txt`
3. `cp .env.example .env` and fill in your real Pokémon Trainer Club credentials.
4. `cp codes.txt.example ~/.pkmn-codes.txt` and fill in your real codes (one per line, replacing
   the example codes already in that file, don't just append to them). This file lives **outside**
   the repo on purpose -- never move your real codes file into the repo tree.

The unit-test suite needs no credentials or browser: `/tmp/venvs/pkmn-tcg-redeem/.venv/bin/python3 -m pytest`.

## Usage

Test without spending any codes first:
```
/tmp/venvs/pkmn-tcg-redeem/.venv/bin/python3 -m pkmn_redeem.cli --dry-run
```
A healthy code comes back `VALID_NOT_REDEEMED` (verified, but intentionally never committed) --
that's the expected "everything works" result for a dry run, not an error.

Redeem for real:
```
/tmp/venvs/pkmn-tcg-redeem/.venv/bin/python3 -m pkmn_redeem.cli
```

Single ad-hoc code (combinable with `--codes-file`):
```
/tmp/venvs/pkmn-tcg-redeem/.venv/bin/python3 -m pkmn_redeem.cli --code ABCDEFGHIJKLM
```

Flags:
- `--codes-file PATH` -- where to read codes from (default `~/.pkmn-codes.txt`).
- `--code CODE` -- add a single code; repeatable, and merged with `--codes-file`.
- `--dry-run` -- verify codes without redeeming them.
- `--debug` -- dump screenshots/HTML per step to `debug-artifacts/` (this always happens
  automatically on a stopping status -- `CAPTCHA_BLOCKED`/`ERROR_FATAL`/`INDETERMINATE` -- regardless
  of the flag). Filenames and HTML content never contain a real code or password. **Screenshots are
  the one exception: a `.png` is a visual capture of the page, so it can and will show a real code
  and your account identity if either is visible on screen at that moment.** Never share
  `debug-artifacts/*.png` in a bug report or public issue.
- `--cdp-port PORT` -- Chrome remote-debugging port (default `9333`). Pass e.g. `--cdp-port 9555`
  if the default is in use by something else.

The printed summary lists each code by its position in the batch (`1`, `2`, ...), not by its
value -- every code is redacted from stdout, so the summary can't be pasted anywhere that leaks
one. It ends with the path to that run's `results/<run-id>.jsonl`, which is the only place the real,
unredacted per-code values live; check it (not the terminal output) to see which code a given row
was. Results persist incrementally as each code resolves -- plus a `results/<run-id>.summary.json`
-- so a run that stops early, crashes, or is interrupted (Ctrl-C) still leaves an accurate record of
what happened, not just what returned successfully.

The Chrome profile used for all of this persists at `~/.local/state/pkmn-tcg-redeem/chrome-profile/`
across runs (on purpose -- session/cookie history helps, not hurts, here) and is never deleted by
this tool. To make that persistence actually work, the tool shuts Chrome down by sending it a CDP
`Browser.close` (Playwright's own `Browser.close()` was tried and does not exit a CDP-attached
Chrome), falling back to OS-level signals only if that fails -- without the graceful close, Chrome
gets killed before it flushes cookies and you get asked to log in again every run.

## Exit codes

- `0` -- every code resolved cleanly (redeemed, natively rejected, or -- dry-run only -- verified
  valid but intentionally not redeemed).
- `1` -- run stopped early (CAPTCHA block or fatal error, so some codes were never attempted), or
  the run never got going at all (missing credentials, no codes, login failure).
- `2` -- at least one code's fate is **unknown** (redeem commit failed after a successful verify).
  Check the account in-game before assuming anything about codes reported this way. This takes
  precedence over `1` when both apply.
