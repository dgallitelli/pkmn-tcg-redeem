from dataclasses import dataclass


@dataclass
class MergeResult:
    codes: list[str]
    warnings: list[str]


def merge_codes(file_lines: list[str], cli_codes: list[str]) -> MergeResult:
    seen: set[str] = set()
    ordered: list[str] = []
    warnings: list[str] = []
    for raw in list(file_lines) + list(cli_codes):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line in seen:
            warnings.append(f"duplicate code skipped: {line}")
            continue
        seen.add(line)
        ordered.append(line)
    return MergeResult(codes=ordered, warnings=warnings)
