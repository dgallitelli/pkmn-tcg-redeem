import http.server
import socket
import subprocess
import sys
import threading
import time

import pytest

from pkmn_redeem.browser import BrowserError, port_busy, profile_pids, wait_for_cdp


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_port_busy_false_when_nothing_listening():
    assert port_busy(_free_port()) is False


def test_port_busy_true_when_something_is_listening():
    port = _free_port()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    try:
        assert port_busy(port) is True
    finally:
        server.close()


def test_profile_pids_finds_process_with_marker_in_argv(tmp_path):
    marker_dir = tmp_path / "marker-profile"
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", f"--user-data-dir={marker_dir}"]
    )
    try:
        time.sleep(0.3)
        found = profile_pids(marker_dir)
        assert proc.pid in found
    finally:
        proc.kill()
        proc.wait(timeout=5)


def test_profile_pids_empty_when_nothing_matches(tmp_path):
    assert profile_pids(tmp_path / "nobody-uses-this-path") == []


def test_profile_pids_rejects_a_different_profile_whose_path_extends_ours(tmp_path):
    decoy_dir = tmp_path / "prof-backup"
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", f"--user-data-dir={decoy_dir}"]
    )
    try:
        time.sleep(0.3)
        assert profile_pids(tmp_path / "prof") == []
        assert proc.pid in profile_pids(decoy_dir)  # sanity: the decoy is still findable by its own path
    finally:
        proc.kill()
        proc.wait(timeout=5)


def test_wait_for_cdp_returns_parsed_json_when_endpoint_responds():
    port = _free_port()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"Browser": "fake/1.0"}')

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        info = wait_for_cdp(port, timeout=5)
        assert info == {"Browser": "fake/1.0"}
    finally:
        server.shutdown()


def test_wait_for_cdp_raises_on_timeout():
    with pytest.raises(BrowserError):
        wait_for_cdp(_free_port(), timeout=1)
