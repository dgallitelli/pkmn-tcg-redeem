from pathlib import Path

from pkmn_redeem import browser
from pkmn_redeem.cli import load_code_list, parse_args


def test_parse_args_defaults():
    args = parse_args([])
    assert args.codes == []
    assert args.dry_run is False
    assert args.debug is False
    assert args.codes_file == Path.home() / ".pkmn-codes.txt"
    assert args.cdp_port == browser.DEFAULT_CDP_PORT


def test_parse_args_accepts_multiple_code_flags_dry_run_and_cdp_port():
    args = parse_args(["--code", "AAA111", "--code", "BBB222", "--dry-run", "--cdp-port", "9555"])
    assert args.codes == ["AAA111", "BBB222"]
    assert args.dry_run is True
    assert args.cdp_port == 9555


def test_load_code_list_merges_file_and_cli(tmp_path, capsys):
    codes_file = tmp_path / "codes.txt"
    codes_file.write_text("FILE1\nFILE1\n# comment\nFILE2\n", encoding="utf-8")
    args = parse_args(["--codes-file", str(codes_file), "--code", "CLI1"])
    result = load_code_list(args)
    assert result == ["FILE1", "FILE2", "CLI1"]
    assert "duplicate" in capsys.readouterr().err


def test_load_code_list_explicit_missing_file_warns(tmp_path, capsys):
    missing = tmp_path / "nope.txt"
    args = parse_args(["--codes-file", str(missing), "--code", "CLI1"])
    result = load_code_list(args)
    assert result == ["CLI1"]
    assert "does not exist" in capsys.readouterr().err


def test_load_code_list_custom_warn_callback_suppresses_printing(tmp_path, capsys):
    codes_file = tmp_path / "codes.txt"
    codes_file.write_text("FILE1\nFILE1\n", encoding="utf-8")
    args = parse_args(["--codes-file", str(codes_file)])
    collected: list[str] = []
    result = load_code_list(args, warn=collected.append)
    assert result == ["FILE1"]
    assert collected == ["duplicate code skipped: FILE1"]
    assert capsys.readouterr().err == ""
