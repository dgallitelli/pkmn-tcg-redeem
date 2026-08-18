from pkmn_redeem.models import CodeResult, CodeStatus
from pkmn_redeem.reporting import compute_exit_code, format_summary_table


def _r(code, status, detail="d"):
    return CodeResult(code=code, status=status, detail=detail, timestamp="t")


def test_exit_code_zero_when_all_terminal_and_safe():
    results = [_r("A", CodeStatus.SUCCESS), _r("B", CodeStatus.REJECTED)]
    assert compute_exit_code(results) == 0


def test_exit_code_zero_includes_valid_not_redeemed_dry_run_status():
    results = [_r("A", CodeStatus.VALID_NOT_REDEEMED), _r("B", CodeStatus.REJECTED)]
    assert compute_exit_code(results) == 0


def test_exit_code_one_when_batch_stopped_with_not_attempted():
    results = [_r("A", CodeStatus.SUCCESS), _r("B", CodeStatus.CAPTCHA_BLOCKED), _r("C", CodeStatus.NOT_ATTEMPTED)]
    assert compute_exit_code(results) == 1


def test_exit_code_one_when_error_transient_present_defensively():
    # ERROR_TRANSIENT should never survive into a persisted CodeResult (flow.py escalates
    # it to ERROR_FATAL on retry failure) -- this is a defensive guard so a future bug in
    # that escalation can't silently report exit code 0.
    results = [_r("A", CodeStatus.SUCCESS), _r("B", CodeStatus.ERROR_TRANSIENT)]
    assert compute_exit_code(results) == 1


def test_exit_code_two_when_any_indeterminate_present():
    results = [_r("A", CodeStatus.SUCCESS), _r("B", CodeStatus.INDETERMINATE)]
    assert compute_exit_code(results) == 2


def test_exit_code_two_outranks_not_attempted():
    results = [_r("A", CodeStatus.INDETERMINATE), _r("B", CodeStatus.NOT_ATTEMPTED)]
    assert compute_exit_code(results) == 2


def test_exit_code_zero_on_empty_results():
    assert compute_exit_code([]) == 0


def test_format_summary_table_includes_every_code_and_status():
    results = [_r("ABC123", CodeStatus.SUCCESS, "redeemed"), _r("DEF456", CodeStatus.REJECTED, "invalid")]
    table = format_summary_table(results)
    assert "ABC123" in table and "SUCCESS" in table and "redeemed" in table
    assert "DEF456" in table and "REJECTED" in table and "invalid" in table
