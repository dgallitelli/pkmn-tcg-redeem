import argparse
import os
import sys
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from . import browser
from .artifacts import ArtifactContext
from .codes import merge_codes
from .models import RunSummary, STOPPING, now_iso
from .reporting import compute_exit_code
from .results import ResultsWriter
from .scrub import Scrubber

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CODES_FILE = Path.home() / ".pkmn-codes.txt"
RESULTS_DIR = REPO_ROOT / "results"
DEBUG_ARTIFACTS_DIR = REPO_ROOT / "debug-artifacts"


def _print_warning(msg: str) -> None:
    print(f"[warn] {msg}", file=sys.stderr)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pkmn-redeem")
    parser.add_argument("--codes-file", type=Path, default=DEFAULT_CODES_FILE)
    parser.add_argument("--code", action="append", default=[], dest="codes")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--cdp-port", type=int, default=browser.DEFAULT_CDP_PORT)
    return parser.parse_args(argv)


def load_code_list(args: argparse.Namespace, warn: Callable[[str], None] = _print_warning) -> list[str]:
    """`warn` defaults to printing immediately (what the unit tests exercise) -- but
    merge_codes' warnings can embed a real code, and at the point this function is
    called, no Scrubber exists yet to redact it. main() overrides `warn` to collect
    warnings instead of printing them, so it can print them scrubbed AFTER the Scrubber
    exists. The file-missing warning is safe to print immediately either way -- it
    contains only a path, never a code."""
    file_lines: list[str] = []
    if args.codes_file.exists():
        file_lines = args.codes_file.read_text(encoding="utf-8").splitlines()
    elif args.codes_file != DEFAULT_CODES_FILE:
        print(f"[warn] --codes-file {args.codes_file} does not exist", file=sys.stderr)
    merged = merge_codes(file_lines, args.codes)
    for warning in merged.warnings:
        warn(warning)
    return merged.codes


def main(argv=None) -> int:
    from playwright.sync_api import sync_playwright

    from .flow import FlowError, dry_run_verify, login, redeem_all

    args = parse_args(argv)
    load_dotenv(REPO_ROOT / ".env")
    username = os.environ.get("PKMN_USERNAME")
    password = os.environ.get("PKMN_PASSWORD")
    if not username or not password:
        print("PKMN_USERNAME / PKMN_PASSWORD not set (check .env)", file=sys.stderr)
        return 1

    pending_warnings: list[str] = []
    codes = load_code_list(args, warn=pending_warnings.append)
    if not codes:
        print("no codes to redeem", file=sys.stderr)
        return 1

    scrubber = Scrubber()
    scrubber.add_secret(password)
    for code in codes:
        scrubber.add_secret(code)
    for warning in pending_warnings:
        print(scrubber.scrub(f"[warn] {warning}"), file=sys.stderr)
    artifacts = ArtifactContext(out_dir=DEBUG_ARTIFACTS_DIR, scrub_fn=scrubber.scrub, debug=args.debug)

    run_id = now_iso().replace(":", "-")
    writer = ResultsWriter(RESULTS_DIR, run_id)
    started_at = now_iso()
    stop_reason: str | None = None
    results = []

    # The run summary must reflect what was actually persisted, not what a flow function
    # managed to return. On Ctrl-C (a normal thing to do to a long batch) or any exception
    # after some codes resolved, redeem_all/dry_run_verify never returns, so `results`
    # stays [] -- but the JSONL already holds real, consumed-code rows. Accumulating in the
    # on_result callback makes the summary independent of that return ever happening.
    live_results: list = []

    def _on_result(result) -> None:
        live_results.append(result)
        writer.append(result)

    cdp_url, proc = browser.launch_or_attach(port=args.cdp_port)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.connect_over_cdp(cdp_url)
            try:
                context = b.contexts[0] if b.contexts else b.new_context()
                page = context.new_page()  # never reuse an existing/restored tab

                try:
                    screen_name = login(page, username, password)
                except FlowError as e:
                    print(scrubber.scrub(f"login failed: {e}"), file=sys.stderr)
                    stop_reason = "LOGIN_FAILED"
                    return 1
                if screen_name:
                    scrubber.add_secret(screen_name)

                if args.dry_run:
                    results = dry_run_verify(page, codes, on_result=_on_result, artifacts=artifacts)
                else:
                    results = redeem_all(page, codes, on_result=_on_result, artifacts=artifacts)

                # Printed by batch index, not by code: every code is a Scrubber secret, so
                # a code-keyed table renders as a wall of identical "[REDACTED]" rows --
                # useless on the INDETERMINATE runs this tool exists to flag. The index
                # matches flow.py's artifact tags (code_<idx>_<status>); the JSONL below is
                # the only place the real code values live.
                for i, r in enumerate(results, 1):
                    print(scrubber.scrub(f"{i:3d}  {r.status.value:20s} {r.detail}"))
                print(f"full results (including real code values): {writer.jsonl_path}")
                return compute_exit_code(results)
            finally:
                # Graceful Chrome close BEFORE the OS-level browser.shutdown() safety net
                # below -- this is what actually lets Chrome flush its cookie/session
                # state to disk before exiting. Without this, shutdown()'s SIGTERM/
                # SIGKILL escalation can kill Chrome before it persists anything,
                # silently defeating the whole point of a persistent profile. Confirmed
                # empirically during Task 10's manual verification: three launch->login
                # ->SIGKILL-shutdown cycles left the profile's cookie store 10.6 hours
                # stale (next launch had to show the login form again).
                #
                # b.close() was tried first and empirically disproven: on a
                # connect_over_cdp() connection, Playwright's Browser.close() only
                # tears down the Playwright-side CDP client connection -- it does not
                # send Chrome any signal to close itself, so the underlying Chrome
                # process (and its still-open pages/profile lock) is left running.
                # Re-verified during Task 11: after b.close(), the Chrome process from
                # browser.launch_or_attach() was still alive and had to be caught by
                # the SIGTERM/SIGKILL fallback in browser.shutdown(), which is exactly
                # the unsafe-teardown path this code exists to avoid.
                #
                # Sending "Browser.close" over a fresh CDP session instead asks Chrome
                # itself to close, which lets it run its normal shutdown path (flushing
                # cookies/session state, releasing the profile lock) before exiting.
                # Verified working: after this call, run 2 of --dry-run skips the
                # login form entirely, confirming the session cookie was persisted.
                try:
                    b.new_browser_cdp_session().send("Browser.close")
                except Exception:
                    pass
    except Exception as e:
        print(scrubber.scrub(f"unexpected error: {type(e).__name__}: {e}"), file=sys.stderr)
        # Never downgrade a finding that was already made: if an INDETERMINATE was recorded
        # before this exception, the caller still needs exit 2, not a generic exit 1.
        return max(1, compute_exit_code(live_results))
    finally:
        # Derived here, not in the try block, and from live_results -- so a Ctrl-C or an
        # exception mid-batch still records the stop reason and the real counts for the
        # codes already written to the JSONL. `stop_reason` set earlier (LOGIN_FAILED) wins,
        # since in that case nothing was ever recorded.
        if stop_reason is None:
            for r in live_results:
                if r.status in STOPPING:
                    stop_reason = r.status.value
                    break
        counts: dict[str, int] = {}
        for r in live_results:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
        writer.write_summary(RunSummary(
            started_at=started_at, ended_at=now_iso(), stop_reason=stop_reason, counts_by_status=counts,
        ))
        browser.shutdown(proc)  # now a safety-net no-op in the common case -- the CDP
                                # "Browser.close" sent above (NOT b.close(), which does
                                # not exit Chrome over a connect_over_cdp connection)
                                # should already have exited Chrome cleanly


if __name__ == "__main__":
    sys.exit(main())
