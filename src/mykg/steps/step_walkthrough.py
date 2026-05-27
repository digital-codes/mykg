"""Thin wrapper that generates a walkthrough.md report for a session."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def run_walkthrough(session_root: Path, log_file: Path | None = None) -> None:
    """Generate walkthrough.md inside session_root. Never raises."""
    try:
        from mykg.walkthrough import generate_walkthrough

        content = generate_walkthrough(session_root, log_file=log_file)
        out = session_root / "walkthrough.md"
        out.write_text(content, encoding="utf-8")
        log.info("Walkthrough report written to %s", out)
    except Exception as exc:
        log.warning("Walkthrough report generation failed: %s", exc)
