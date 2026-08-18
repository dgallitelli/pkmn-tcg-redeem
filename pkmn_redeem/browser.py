import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE_DIR = Path.home() / ".local/state/pkmn-tcg-redeem/chrome-profile"
DEFAULT_CDP_PORT = 9333


class BrowserError(RuntimeError):
    pass


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def profile_pids(profile_dir: Path = PROFILE_DIR) -> list[int]:
    """PIDs whose command line contains our profile's --user-data-dir as an exact argv
    token, verified via `ps` (not just `pgrep`) so this can never mis-target an unrelated
    process. Token match, not substring match: a raw substring check would also match a
    DIFFERENT profile whose path merely starts with ours (e.g. querying
    ".../chrome-profile" would match a running ".../chrome-profile-backup") -- `ps -o
    command=` output is space-separated argv, and the profile path itself never contains
    spaces, so splitting on whitespace and requiring an exact element match closes that
    false positive."""
    marker = f"--user-data-dir={profile_dir}"
    found = subprocess.run(["pgrep", "-f", "--", marker], capture_output=True, text=True)
    pids: list[int] = []
    for tok in found.stdout.split():
        try:
            pid = int(tok)
        except ValueError:
            continue
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
        if marker in cmd.split():
            pids.append(pid)
    return pids


def wait_for_cdp(port: int, timeout: float = 45) -> dict:
    endpoint = f"http://127.0.0.1:{port}/json/version"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(endpoint, timeout=2) as r:
                return json.loads(r.read().decode())
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            time.sleep(0.2)
    raise BrowserError(f"CDP endpoint on port {port} never became ready within {timeout}s")


def launch_or_attach(
    port: int = DEFAULT_CDP_PORT, profile_dir: Path = PROFILE_DIR
) -> tuple[str, Optional[subprocess.Popen]]:
    """Returns (cdp_http_url, proc). proc is None when attaching to an already-running
    instance this call didn't start. shutdown() always terminates by profile-marker match
    regardless of proc -- proc is only used to await this process's own exit when we did
    start it; it is NOT what gates whether shutdown() kills anything (see shutdown())."""
    existing = profile_pids(profile_dir)
    if existing:
        if not port_busy(port):
            raise BrowserError(
                f"Chrome already running against {profile_dir} (pids={existing}) "
                f"but port {port} isn't answering -- investigate before rerunning."
            )
        wait_for_cdp(port)
        return f"http://127.0.0.1:{port}", None

    if port_busy(port):
        raise BrowserError(f"port {port} is in use by something unrelated -- pass --cdp-port to use a different one")

    profile_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            CHROME_BIN,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--hide-crash-restore-bubble",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        wait_for_cdp(port)
    except BrowserError:
        proc.kill()
        raise
    return f"http://127.0.0.1:{port}", proc


def shutdown(proc: Optional[subprocess.Popen], profile_dir: Path = PROFILE_DIR) -> None:
    """Quits the Chrome process this run started or attached to -- matched by profile
    marker, not by `proc` identity (proc is None on the attach path). `proc`, when not
    None, is only used below to await this run's own subprocess handle. Never deletes
    the profile directory -- it's meant to persist across runs (spec: Credentials &
    session persistence).

    Callers are expected to have already sent a real CDP `Browser.close` before calling
    this (see cli.main) -- that's what lets Chrome flush cookies/session state to disk.
    This function's job is twofold: give that graceful close a few seconds to actually
    finish exiting on its own (the grace-period poll below) before ever touching a
    signal, and act as the fallback safety net (SIGTERM then SIGKILL) if it doesn't."""
    grace_deadline = time.time() + 3.0
    while profile_pids(profile_dir) and time.time() < grace_deadline:
        time.sleep(0.2)

    for sig in (signal.SIGTERM, signal.SIGKILL):
        pids = profile_pids(profile_dir)
        if not pids:
            break
        for pid in pids:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        time.sleep(2.5 if sig is signal.SIGTERM else 1.0)
    if proc is not None:
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
