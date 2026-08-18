import random
import time
from typing import Callable, Optional

from .artifacts import ArtifactContext
from .classify import classify_redeem_response, classify_verify_response
from .models import CodeResult, CodeStatus, STOPPING, now_iso

LOGIN_URL = "https://redeem.tcg.pokemon.com/en-us/"
CHUNK_SIZE = 10


class FlowError(RuntimeError):
    pass


def pace() -> None:
    """Small randomized delay between requests -- politeness against the WAF (Imperva/
    Incapsula, confirmed present) and reCAPTCHA scoring, not fingerprint/timing evasion."""
    time.sleep(random.uniform(2.0, 4.0))


def _settle(page, timeout: int = 20000) -> None:
    """Best-effort wait -- this site's analytics/reCAPTCHA/Incapsula beacons can prevent
    networkidle from ever firing, so a timeout here must never kill the run (carried over
    from the spike's proven settle(), which existed for exactly this reason)."""
    for state in ("domcontentloaded", "networkidle"):
        try:
            page.wait_for_load_state(state, timeout=timeout)
        except Exception:
            pass
    page.wait_for_timeout(1000)


def _first_visible(page, builders):
    for build in builders:
        for frame in page.frames:
            try:
                loc = build(frame).first
                if loc.count() and loc.is_visible():
                    return loc
            except Exception:
                continue
    return None


def dismiss_cookie_banner(page) -> None:
    for sel in ("#onetrust-reject-all-handler", ".onetrust-close-btn-handler"):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=5000)
                page.wait_for_timeout(1000)
                return
        except Exception:
            continue


def _already_authenticated(page) -> bool:
    """True once the persistent profile's session is already logged in -- LOGIN_URL then
    lands directly on the redemption view instead of a login form. This is the common
    case from run 2 onward, precisely because the profile persists -- it is NOT an error."""
    for sel in ("input#code", "[data-testid='code-redemption-view']"):
        try:
            if page.locator(sel).first.count():
                return True
        except Exception:
            continue
    return False


def _try_extract_screen_name(page) -> Optional[str]:
    """Best-effort only -- there's no confirmed stable selector for this (unlike the
    redemption-flow elements), so failure to find it is expected and must not raise."""
    for sel in ("[data-testid='user-menu']", "[data-testid='account-menu']"):
        try:
            loc = page.locator(sel).first
            if loc.count():
                text = loc.inner_text(timeout=2000).strip()
                if text:
                    return text
        except Exception:
            continue
    return None


def login(page, username: str, password: str) -> Optional[str]:
    """No-ops the actual login form-fill if the persistent profile's session is already
    authenticated. Returns the account's screen name if found (best-effort), for the
    caller to add to a Scrubber -- returns None if it couldn't be found, which is not
    itself an error."""
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    _settle(page)

    if not _already_authenticated(page):
        user_loc = _first_visible(page, [
            lambda f: f.locator("input#email"),
            lambda f: f.locator("input[name='email'], input[name='username']"),
            lambda f: f.locator("input[type='email']"),
        ])
        pass_loc = _first_visible(page, [
            lambda f: f.locator("input#password"),
            lambda f: f.locator("input[type='password']"),
        ])
        if user_loc is None or pass_loc is None:
            raise FlowError("login form not found and not already authenticated -- site markup may have changed")

        try:
            user_loc.fill(username)
            pass_loc.fill(password)
        except Exception as e:
            raise FlowError(f"login fill failed: {type(e).__name__}") from None

        submit = _first_visible(page, [
            lambda f: f.locator("input#accept"),
            lambda f: f.get_by_role("button", name="Log In", exact=False),
        ])
        try:
            if submit is not None:
                submit.click()
            else:
                pass_loc.press("Enter")
        except Exception as e:
            raise FlowError(f"login submit failed: {type(e).__name__}") from None

        _settle(page, timeout=30000)

    dismiss_cookie_banner(page)
    return _try_extract_screen_name(page)


class ResponseCapture:
    """Always-on response listener -- owns classification's data source regardless of
    --debug. Reset-before-act (see submit_one_code/commit_redeem) means a response for
    the code just submitted cannot be missed by a stale value from a prior code; matching
    responses by couponCode in classify.py means even a late-arriving stale response can
    only ever produce a safe stop (ERROR_FATAL/INDETERMINATE), never a false SUCCESS."""

    def __init__(self, page) -> None:
        self.last_verify: Optional[dict] = None
        self.last_redeem: Optional[dict] = None
        page.on("response", self._on_response)

    def _on_response(self, response) -> None:
        url = response.url
        try:
            if "/commerce/v1/external/webccr/verify" in url:
                self.last_verify = response.json()
            elif "/commerce/v1/external/webccr/redeem" in url:
                self.last_redeem = response.json()
        except Exception:
            pass


def submit_one_code(page, capture: "ResponseCapture", code: str) -> tuple[Optional[CodeStatus], str]:
    capture.last_verify = None
    try:
        code_loc = page.locator("input#code").first
        if not code_loc.count():
            return CodeStatus.ERROR_FATAL, "code input field not found"
        code_loc.fill(code)
        verify_btn = page.locator("[data-testid='verify-code-button']").first
        if verify_btn.count():
            verify_btn.click()
        else:
            code_loc.press("Enter")
    except Exception as e:
        # Anything here is pre-Redeem -- nothing consumed, genuinely retry-safe.
        return CodeStatus.ERROR_TRANSIENT, f"submit action failed: {type(e).__name__}"

    deadline = time.time() + 20
    while capture.last_verify is None and time.time() < deadline:
        page.wait_for_timeout(200)
    if capture.last_verify is None:
        return CodeStatus.ERROR_TRANSIENT, "no verify response observed within timeout"

    return classify_verify_response(capture.last_verify, code)


def submit_one_code_with_retry(page, capture: "ResponseCapture", code: str) -> tuple[Optional[CodeStatus], str]:
    status, detail = submit_one_code(page, capture, code)
    if status == CodeStatus.ERROR_TRANSIENT:
        pace()
        status, detail = submit_one_code(page, capture, code)
        if status == CodeStatus.ERROR_TRANSIENT:
            return CodeStatus.ERROR_FATAL, f"transient error recurred: {detail}"
    return status, detail


def commit_redeem(page, capture: "ResponseCapture", codes: list[str]) -> dict[str, tuple[CodeStatus, str]]:
    """Anything that fails here is at-or-after the Redeem click, so per spec it's always
    INDETERMINATE, never retried -- unlike submit_one_code, there's no transient case."""
    capture.last_redeem = None
    redeem_btn = page.locator("[data-testid='button-redeem']").first
    try:
        redeem_btn.wait_for(state="visible", timeout=10000)
        deadline = time.time() + 10
        while not redeem_btn.is_enabled() and time.time() < deadline:
            page.wait_for_timeout(200)
        if not redeem_btn.is_enabled():
            return {c: (CodeStatus.INDETERMINATE, "Redeem button never became enabled") for c in codes}
        redeem_btn.click()
    except Exception as e:
        return {c: (CodeStatus.INDETERMINATE, f"redeem click failed: {type(e).__name__}") for c in codes}

    deadline = time.time() + 20
    while capture.last_redeem is None and time.time() < deadline:
        page.wait_for_timeout(200)
    if capture.last_redeem is None:
        return {c: (CodeStatus.INDETERMINATE, "no redeem response observed within timeout") for c in codes}

    response = capture.last_redeem
    return {c: classify_redeem_response(response, c) for c in codes}


def clear_table(page) -> None:
    """Non-consuming: clears pending verified rows. Used between dry-run chunks so a
    codes list longer than 10 doesn't jam against the site's own pending-rows limit."""
    try:
        btn = page.locator("[data-testid='button-clear-table']").first
        if btn.count() and btn.is_visible():
            btn.click(timeout=5000)
            page.wait_for_timeout(1000)
    except Exception:
        pass


def redeem_all(
    page,
    codes: list[str],
    on_result: Callable[[CodeResult], None],
    artifacts: Optional[ArtifactContext] = None,
) -> list[CodeResult]:
    """Drives the full chunked submit->redeem flow. Calls on_result as each code resolves
    -- this is what makes results crash-safe; a caller MUST pass something that persists
    (e.g. ResultsWriter.append), since this function's return value alone is not durable
    if the process dies partway through."""
    capture = ResponseCapture(page)
    resolved: list[CodeResult] = []
    remaining = list(codes)
    stop = False

    def _record(code: str, status: CodeStatus, detail: str) -> None:
        # Tags are interpolated straight into artifact filenames, so they are keyed on the
        # code's 1-based position in this run's batch, never on the code value itself --
        # a debug-artifacts filename must never be able to leak a real code (the Scrubber
        # only redacts file *contents*). results/<run-id>.jsonl is the mapping back to the
        # real code. NOT_ATTEMPTED never dumps: nothing was submitted, so every such dump
        # would be an identical, evidence-free copy of the same post-stop page.
        idx = len(resolved) + 1
        result = CodeResult(code=code, status=status, detail=detail, timestamp=now_iso())
        resolved.append(result)
        on_result(result)
        if artifacts is not None and status != CodeStatus.NOT_ATTEMPTED:
            if status in STOPPING:
                artifacts.dump_always(page, f"code_{idx}_{status.value}")
            else:
                artifacts.maybe_dump(page, f"code_{idx}_{status.value}")

    while remaining and not stop:
        chunk, remaining = remaining[:CHUNK_SIZE], remaining[CHUNK_SIZE:]
        pending: list[str] = []

        for code in chunk:
            status, detail = submit_one_code_with_retry(page, capture, code)
            if status is None:
                pending.append(code)
            else:
                _record(code, status, detail)
                if status in STOPPING:
                    stop = True
                    break
            pace()

        if not stop and pending:
            outcomes = commit_redeem(page, capture, pending)
            for code in pending:
                status, detail = outcomes[code]
                _record(code, status, detail)
            if any(status in STOPPING for status, _ in outcomes.values()):
                stop = True
        elif stop and pending:
            # These codes verified valid but the chunk stopped before a Redeem commit was
            # ever attempted for them -- nothing consumed, but plain "not attempted"
            # undersells that they're sitting in the site's pending table, not untouched.
            for code in pending:
                _record(code, CodeStatus.NOT_ATTEMPTED,
                        "verified valid but batch stopped before Redeem was attempted for this code")

        if not stop:
            pace()

    attempted = {r.code for r in resolved}
    for code in codes:
        if code not in attempted:
            _record(code, CodeStatus.NOT_ATTEMPTED, "batch stopped before this code was submitted")
    return resolved


def dry_run_verify(
    page,
    codes: list[str],
    on_result: Callable[[CodeResult], None],
    artifacts: Optional[ArtifactContext] = None,
) -> list[CodeResult]:
    """Verify-only: never clicks Redeem, so no code is ever consumed. Chunks at the same
    limit as a real run and clears the table between chunks (also non-consuming) -- rows
    only clear on a Redeem commit or an explicit Clear Table, and dry-run never does the
    former, so without this a codes list over 10 long jams silently on the 11th."""
    capture = ResponseCapture(page)
    resolved: list[CodeResult] = []
    remaining = list(codes)
    stop = False

    def _record(code: str, status: CodeStatus, detail: str) -> None:
        # Same rule as redeem_all's _record: batch index, never the code value, reaches a
        # filename; every STOPPING status dumps unconditionally (INDETERMINATE most of all
        # -- that's the one needing manual reconciliation); NOT_ATTEMPTED never dumps.
        idx = len(resolved) + 1
        result = CodeResult(code=code, status=status, detail=detail, timestamp=now_iso())
        resolved.append(result)
        on_result(result)
        if artifacts is not None and status != CodeStatus.NOT_ATTEMPTED:
            if status in STOPPING:
                artifacts.dump_always(page, f"code_{idx}_{status.value}")
            else:
                artifacts.maybe_dump(page, f"code_{idx}_{status.value}")

    while remaining and not stop:
        chunk, remaining = remaining[:CHUNK_SIZE], remaining[CHUNK_SIZE:]
        for code in chunk:
            status, detail = submit_one_code_with_retry(page, capture, code)
            if status is None:
                status, detail = CodeStatus.VALID_NOT_REDEEMED, "valid (dry-run -- not redeemed)"
            _record(code, status, detail)
            if status in STOPPING:
                stop = True
                break
            pace()
        if not stop and remaining:
            clear_table(page)
            pace()

    attempted = {r.code for r in resolved}
    for code in codes:
        if code not in attempted:
            _record(code, CodeStatus.NOT_ATTEMPTED, "dry-run stopped before this code")
    return resolved
