import json
from pathlib import Path

from .models import CodeResult, RunSummary


class ResultsWriter:
    def __init__(self, results_dir: Path, run_id: str) -> None:
        self.results_dir = Path(results_dir)
        self.run_id = run_id
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.results_dir / f"{run_id}.jsonl"
        self.summary_path = self.results_dir / f"{run_id}.summary.json"

    def append(self, result: CodeResult) -> None:
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result.to_dict()) + "\n")

    def write_summary(self, summary: RunSummary) -> None:
        self.summary_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
