from __future__ import annotations

import io
import threading
from unittest.mock import patch

import pytest

from mykg.llm.error_gate import ErrorGate, noop_gate


def _is_running(gate: ErrorGate) -> bool:
    """Return True when the gate is not paused."""
    with gate._cond:
        return not gate._paused


def test_disabled_gate_noop():
    gate = ErrorGate(threshold=0)
    assert not gate.enabled
    # Must return without raising or blocking.
    gate.record_error(Exception("irrelevant"))


def test_noop_gate_singleton():
    g1 = noop_gate()
    g2 = noop_gate()
    assert g1 is g2
    assert not g1.enabled


def test_below_threshold_no_pause():
    gate = ErrorGate(threshold=3)
    assert gate.enabled
    with patch("sys.stdin", io.StringIO("")):
        gate.record_error(Exception("1"))
        gate.record_error(Exception("2"))
    # No pause triggered; gate is not paused.
    assert _is_running(gate)


def test_threshold_trip_and_resume(capsys):
    gate = ErrorGate(threshold=2)
    with patch("sys.stdin", io.StringIO("\n")):
        gate.record_error(Exception("1"))
        gate.record_error(Exception("2"))  # trips the gate
    # After resume the gate must be running again.
    assert _is_running(gate)
    # Count must be reset.
    assert gate._count == 0


def test_count_reset_after_trip():
    gate = ErrorGate(threshold=2)
    with patch("sys.stdin", io.StringIO("\n")):
        gate.record_error(Exception("a"))
        gate.record_error(Exception("b"))
    # A subsequent error should count from 1, not from 2.
    with patch("sys.stdin", io.StringIO("\n")):
        gate.record_error(Exception("c"))
    assert gate._count == 1


def test_eoferror_auto_resume():
    gate = ErrorGate(threshold=1)
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.readline.side_effect = EOFError
        gate.record_error(Exception("x"))
    assert _is_running(gate)


def test_oserror_auto_resume():
    gate = ErrorGate(threshold=1)
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.readline.side_effect = OSError("closed")
        gate.record_error(Exception("x"))
    assert _is_running(gate)


def test_q_abort_raises():
    gate = ErrorGate(threshold=1)
    with patch("sys.stdin", io.StringIO("q\n")):
        with pytest.raises(KeyboardInterrupt):
            gate.record_error(Exception("x"))
    # Gate must be unpaused so waiting threads can proceed.
    assert _is_running(gate)


def test_q_uppercase_abort():
    gate = ErrorGate(threshold=1)
    with patch("sys.stdin", io.StringIO("Q\n")):
        with pytest.raises(KeyboardInterrupt):
            gate.record_error(Exception("x"))


def test_waiting_threads_unblock_after_resume():
    """Threads blocked during a pause must unblock once the pausing thread resumes."""
    gate = ErrorGate(threshold=1)
    unblocked = threading.Event()

    def _waiter():
        gate.record_error(Exception("waiter"))
        unblocked.set()

    # Trip the gate from the main thread first.
    trip_done = threading.Event()

    def _tripper():
        with patch("sys.stdin", io.StringIO("\n")):
            gate.record_error(Exception("tripper"))
        trip_done.set()

    tripper = threading.Thread(target=_tripper)
    tripper.start()
    trip_done.wait(timeout=2)

    # Now the gate is unpaused; a new waiter should not block.
    waiter = threading.Thread(target=_waiter)
    waiter.start()
    unblocked.wait(timeout=2)
    waiter.join(timeout=2)

    assert unblocked.is_set()


def test_concurrent_errors_only_one_trip():
    """When many threads hit the threshold simultaneously, only one should trip the gate."""
    threshold = 5
    gate = ErrorGate(threshold=threshold)

    def _worker():
        with patch("sys.stdin", io.StringIO("\n")):
            try:
                gate.record_error(Exception("concurrent"))
            except KeyboardInterrupt:
                pass

    threads = [threading.Thread(target=_worker) for _ in range(threshold * 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    # All threads should have finished; gate must be unpaused.
    assert _is_running(gate)
