from .models import CodeResult, CodeStatus


def compute_exit_code(results: list[CodeResult]) -> int:
    """Distinct from models.STOPPING, which governs whether a batch stops *mid-run*.
    This governs what's worth flagging to the caller once a run is over -- e.g.
    NOT_ATTEMPTED (a batch-stopped side effect) belongs here but not in STOPPING itself.
    ERROR_TRANSIENT is included defensively even though it should never reach a persisted
    CodeResult (flow.py's retry-once logic escalates it to ERROR_FATAL first)."""
    statuses = {r.status for r in results}
    if CodeStatus.INDETERMINATE in statuses:
        return 2
    if statuses & {CodeStatus.CAPTCHA_BLOCKED, CodeStatus.ERROR_FATAL, CodeStatus.ERROR_TRANSIENT, CodeStatus.NOT_ATTEMPTED}:
        return 1
    return 0


def format_summary_table(results: list[CodeResult]) -> str:
    if not results:
        return "(no codes processed)"
    lines = [f"{r.code:20s} {r.status.value:20s} {r.detail}" for r in results]
    return "\n".join(lines)
