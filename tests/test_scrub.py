from pkmn_redeem.scrub import Scrubber


def test_scrub_redacts_added_secrets():
    s = Scrubber()
    s.add_secret("hunter2")
    s.add_secret("ABCDEFGHIJKLM")
    text = "logging in with hunter2, code ABCDEFGHIJKLM accepted"
    assert s.scrub(text) == "logging in with [REDACTED], code [REDACTED] accepted"


def test_scrub_ignores_empty_secret():
    s = Scrubber()
    s.add_secret("")
    assert s.scrub("hello") == "hello"


def test_scrub_ignores_too_short_secret():
    """A short value would make the naive substring replace shred unrelated text, so
    add_secret must refuse it rather than register a 2-char 'secret'."""
    s = Scrubber()
    s.add_secret("ab")
    assert s.scrub("text with ab in it") == "text with ab in it"


def test_scrub_coerces_non_string_input():
    s = Scrubber()
    s.add_secret("secretvalue")
    err = ValueError("failed on secretvalue")
    assert s.scrub(err) == "failed on [REDACTED]"


def test_scrub_with_no_secrets_added_is_passthrough():
    s = Scrubber()
    assert s.scrub("nothing to hide") == "nothing to hide"
