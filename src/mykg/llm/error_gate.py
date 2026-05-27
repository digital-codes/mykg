from __future__ import annotations

import sys
import threading

from mykg.logging import get

log = get("mykg.llm.error_gate")


class ErrorGate:
    """Thread-safe global gate that accumulates API errors across all workers.

    When the accumulated error count reaches the threshold, the thread that
    trips the gate pauses all workers by reading from stdin (waiting for the
    user to press Enter). Other threads block on a Condition until resumed.

    If the gate is disabled (threshold=0 or enabled=False), record_error is a no-op.
    """

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold
        self._count = 0
        self._cond = threading.Condition(threading.Lock())
        self._paused = False

    @property
    def enabled(self) -> bool:
        return self._threshold > 0

    def record_error(self, exc: BaseException) -> None:
        """Increment error counter; pause all workers if threshold is reached."""
        if not self.enabled:
            return

        with self._cond:
            # Block if another thread already triggered a pause.
            while self._paused:
                self._cond.wait()

            self._count += 1
            count = self._count
            if count < self._threshold:
                return
            # This thread trips the gate — reset count and mark paused atomically.
            self._count = 0
            self._paused = True

        # Only one thread reaches here per pause cycle (the one that set _paused).
        log.warning(
            "ERROR GATE — %d API errors accumulated (threshold=%d)",
            count,
            self._threshold,
        )
        print(
            f"\n[PAUSED] {count} API error(s) accumulated "
            f"(threshold={self._threshold}). "
            "Press Enter to resume, or type 'q' + Enter to abort: ",
            end="",
            flush=True,
        )
        try:
            line = sys.stdin.readline()
        except (EOFError, OSError):
            # Non-interactive context (e.g. piped input) — auto-resume after logging.
            log.warning("ERROR GATE — non-interactive stdin; auto-resuming")
            line = ""

        if line.strip().lower() == "q":
            log.warning("ERROR GATE — user aborted pipeline")
            with self._cond:
                self._paused = False
                self._cond.notify_all()
            raise KeyboardInterrupt("Pipeline aborted by user at error gate")

        log.info("ERROR GATE — resuming pipeline")
        with self._cond:
            self._paused = False
            self._cond.notify_all()


_NOOP_GATE = ErrorGate(threshold=0)


def noop_gate() -> ErrorGate:
    """Return a shared disabled gate for callers that have no gate configured."""
    return _NOOP_GATE
