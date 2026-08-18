from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class CodeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    CAPTCHA_BLOCKED = "CAPTCHA_BLOCKED"
    INDETERMINATE = "INDETERMINATE"
    ERROR_TRANSIENT = "ERROR_TRANSIENT"
    ERROR_FATAL = "ERROR_FATAL"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    VALID_NOT_REDEEMED = "VALID_NOT_REDEEMED"  # --dry-run only: verify said valid, redeem never attempted by design


STOPPING = {CodeStatus.CAPTCHA_BLOCKED, CodeStatus.ERROR_FATAL, CodeStatus.INDETERMINATE}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CodeResult:
    code: str
    status: CodeStatus
    detail: str
    timestamp: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class RunSummary:
    started_at: str
    ended_at: Optional[str]
    stop_reason: Optional[str]
    counts_by_status: dict

    def to_dict(self) -> dict:
        return asdict(self)
