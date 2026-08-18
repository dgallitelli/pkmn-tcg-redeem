import json

from pkmn_redeem.models import CodeResult, CodeStatus, RunSummary
from pkmn_redeem.results import ResultsWriter


def test_append_writes_one_jsonl_line_per_call(tmp_path):
    writer = ResultsWriter(tmp_path, "run1")
    writer.append(CodeResult(code="A", status=CodeStatus.SUCCESS, detail="redeemed", timestamp="t0"))
    writer.append(CodeResult(code="B", status=CodeStatus.REJECTED, detail="invalid", timestamp="t1"))

    lines = writer.jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"code": "A", "status": "SUCCESS", "detail": "redeemed", "timestamp": "t0"}
    assert json.loads(lines[1]) == {"code": "B", "status": "REJECTED", "detail": "invalid", "timestamp": "t1"}


def test_append_survives_across_writer_instances(tmp_path):
    ResultsWriter(tmp_path, "run1").append(CodeResult(code="A", status=CodeStatus.SUCCESS, detail="x", timestamp="t0"))
    ResultsWriter(tmp_path, "run1").append(CodeResult(code="B", status=CodeStatus.SUCCESS, detail="y", timestamp="t1"))
    lines = (tmp_path / "run1.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_write_summary(tmp_path):
    writer = ResultsWriter(tmp_path, "run1")
    writer.write_summary(RunSummary(started_at="t0", ended_at="t1", stop_reason=None, counts_by_status={"SUCCESS": 2}))
    data = json.loads(writer.summary_path.read_text(encoding="utf-8"))
    assert data == {"started_at": "t0", "ended_at": "t1", "stop_reason": None, "counts_by_status": {"SUCCESS": 2}}


def test_results_dir_is_created_if_missing(tmp_path):
    nested = tmp_path / "does" / "not" / "exist"
    ResultsWriter(nested, "run1")
    assert nested.is_dir()
