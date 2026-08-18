from pathlib import Path

from pkmn_redeem.artifacts import ArtifactContext, write_text


def test_write_text_creates_parent_dirs_and_scrubs_content(tmp_path):
    target = tmp_path / "nested" / "dir" / "out.html"
    write_text(target, "password is hunter2", lambda s: s.replace("hunter2", "[REDACTED]"))
    assert target.read_text(encoding="utf-8") == "password is [REDACTED]"


def test_write_text_overwrites_existing_file(tmp_path):
    target = tmp_path / "out.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_text(target, "first", lambda s: s)
    write_text(target, "second", lambda s: s)
    assert target.read_text(encoding="utf-8") == "second"


class _FakePage:
    """Stands in for a Playwright Page -- ArtifactContext only ever calls these two methods."""

    def screenshot(self, path, full_page=True):
        Path(path).write_bytes(b"fake-png-bytes")

    def content(self):
        return "<html>secret-value</html>"


def test_artifact_context_maybe_dump_noop_when_debug_false(tmp_path):
    ctx = ArtifactContext(out_dir=tmp_path, scrub_fn=lambda s: s, debug=False)
    ctx.maybe_dump(_FakePage(), "checkpoint")
    assert list(tmp_path.iterdir()) == []


def test_artifact_context_maybe_dump_writes_scrubbed_when_debug_true(tmp_path):
    ctx = ArtifactContext(out_dir=tmp_path, scrub_fn=lambda s: s.replace("secret-value", "[REDACTED]"), debug=True)
    ctx.maybe_dump(_FakePage(), "checkpoint")
    assert (tmp_path / "checkpoint.png").exists()
    assert (tmp_path / "checkpoint.html").read_text(encoding="utf-8") == "<html>[REDACTED]</html>"


def test_artifact_context_dump_always_writes_regardless_of_debug_flag():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        ctx = ArtifactContext(out_dir=Path(d), scrub_fn=lambda s: s, debug=False)
        ctx.dump_always(_FakePage(), "error")
        assert (Path(d) / "error.png").exists()
