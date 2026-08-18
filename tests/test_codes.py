from pkmn_redeem.codes import merge_codes


def test_merge_trims_whitespace():
    result = merge_codes(["  ABC123  "], [])
    assert result.codes == ["ABC123"]


def test_merge_skips_blank_and_comment_lines():
    result = merge_codes(["", "  ", "# a comment", "ABC123"], [])
    assert result.codes == ["ABC123"]


def test_merge_preserves_file_then_cli_order():
    result = merge_codes(["FILE1", "FILE2"], ["CLI1"])
    assert result.codes == ["FILE1", "FILE2", "CLI1"]


def test_merge_dedupes_preserving_first_occurrence_and_warns():
    result = merge_codes(["ABC123", "DEF456"], ["ABC123"])
    assert result.codes == ["ABC123", "DEF456"]
    assert result.warnings == ["duplicate code skipped: ABC123"]


def test_merge_empty_inputs_returns_empty():
    result = merge_codes([], [])
    assert result.codes == []
    assert result.warnings == []
