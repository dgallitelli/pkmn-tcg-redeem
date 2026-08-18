from dataclasses import dataclass
from pathlib import Path
from typing import Callable


def write_text(path: Path, content: str, scrub_fn: Callable[[str], str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scrub_fn(content), encoding="utf-8")


def dump_checkpoint(page, tag: str, out_dir: Path, scrub_fn: Callable[[str], str]) -> None:
    """Screenshot + HTML for one checkpoint. Never raises -- this is a debugging aid,
    never allowed to take down the main flow it's instrumenting."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(out_dir / f"{tag}.png"), full_page=True)
    except Exception:
        pass
    try:
        write_text(out_dir / f"{tag}.html", page.content(), scrub_fn)
    except Exception:
        pass


@dataclass
class ArtifactContext:
    """Gates routine checkpoint dumping behind --debug. dump_always() bypasses that gate
    entirely -- it's what flow.py calls on every batch-stopping status (CAPTCHA_BLOCKED,
    ERROR_FATAL, INDETERMINATE), per spec: those dumps must happen regardless of the flag,
    since that's exactly when the evidence is needed. Tags must not embed a real code --
    they'd land in a filename, which scrub_fn (content-only) cannot redact."""

    out_dir: Path
    scrub_fn: Callable[[str], str]
    debug: bool

    def maybe_dump(self, page, tag: str) -> None:
        if self.debug:
            dump_checkpoint(page, tag, self.out_dir, self.scrub_fn)

    def dump_always(self, page, tag: str) -> None:
        dump_checkpoint(page, tag, self.out_dir, self.scrub_fn)
