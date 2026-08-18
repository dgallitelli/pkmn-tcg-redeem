from pkmn_redeem.models import CodeStatus, CodeResult, RunSummary, STOPPING, now_iso


def test_code_status_values_are_strings():
    assert CodeStatus.SUCCESS.value == "SUCCESS"
    assert CodeStatus.INDETERMINATE.value == "INDETERMINATE"
    assert CodeStatus.VALID_NOT_REDEEMED.value == "VALID_NOT_REDEEMED"


def test_stopping_set_contains_the_three_batch_stopping_statuses():
    assert STOPPING == {CodeStatus.CAPTCHA_BLOCKED, CodeStatus.ERROR_FATAL, CodeStatus.INDETERMINATE}


def test_code_result_to_dict_serializes_status_as_plain_string():
    r = CodeResult(code="ABC123", status=CodeStatus.SUCCESS, detail="redeemed", timestamp="2026-08-17T00:00:00+00:00")
    d = r.to_dict()
    assert d == {
        "code": "ABC123",
        "status": "SUCCESS",
        "detail": "redeemed",
        "timestamp": "2026-08-17T00:00:00+00:00",
    }
    assert type(d["status"]) is str


def test_run_summary_to_dict():
    s = RunSummary(started_at="t0", ended_at="t1", stop_reason=None, counts_by_status={"SUCCESS": 3})
    assert s.to_dict() == {"started_at": "t0", "ended_at": "t1", "stop_reason": None, "counts_by_status": {"SUCCESS": 3}}


def test_now_iso_returns_iso8601_with_utc_offset():
    ts = now_iso()
    assert "T" in ts
    assert ts.endswith("+00:00")
