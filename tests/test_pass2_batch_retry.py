"""Tests for in-run retry of failed batches in run_pass2_batched."""

import unittest.mock as mock
from unittest.mock import MagicMock

import mykg.pass2 as p2_mod
from mykg.pass2 import run_pass2_batched


def test_failed_batches_are_retried():
    """After initial pass, failed batches are retried up to batch_retry_max times."""
    files = {
        "a.md": "# A\ncontent about Alice",
        "b.md": "# B\ncontent about Bob",
    }
    schema = {
        "concepts": [{"type": "Person", "attributes": ["name"], "parent": None}],
        "properties": [],
    }
    flat = {"Person": ["name"]}

    extract_calls = []

    def counting_extract(batch, *args, **kwargs):
        extract_calls.append(len(batch))
        if len(extract_calls) <= 2:  # first round: both batches fail
            raise RuntimeError("simulated timeout")
        return {"nodes": [], "edges": []}  # retry succeeds

    with mock.patch.object(p2_mod, "_extract_batch", side_effect=counting_extract):
        results, _, _, _ = run_pass2_batched(
            files,
            schema,
            flat,
            MagicMock(),
            batch_token_target=8,  # small enough to force one file per batch
            batch_retry_max=1,
            max_workers=2,
        )

    # 2 initial failures + 2 retry calls = 4 total
    assert len(extract_calls) == 4, (
        f"Expected 4 _extract_batch calls (2 initial + 2 retry) but got {len(extract_calls)}"
    )
    assert "a.md" in results
    assert "b.md" in results


def test_retry_disabled_when_batch_retry_max_is_zero():
    """When batch_retry_max=0 no retry loop runs."""
    files = {"a.md": "# A\nsome content"}
    schema = {"concepts": [], "properties": []}
    flat = {}

    extract_calls = []

    def always_fail(*args, **kwargs):
        extract_calls.append(1)
        raise RuntimeError("always fails")

    with mock.patch.object(p2_mod, "_extract_batch", side_effect=always_fail):
        run_pass2_batched(
            files,
            schema,
            flat,
            MagicMock(),
            batch_token_target=100_000,
            batch_retry_max=0,
            max_workers=1,
        )

    assert len(extract_calls) == 1, f"Expected 1 call (no retry) but got {len(extract_calls)}"


def test_retry_runs_n_rounds_per_batch_retry_max():
    """batch_retry_max=2 means up to 2 retry rounds after the initial attempt."""
    files = {"a.md": "# A\nsome content"}
    schema = {"concepts": [], "properties": []}
    flat = {}

    extract_calls = []

    def fail_twice_then_succeed(*args, **kwargs):
        extract_calls.append(1)
        if len(extract_calls) < 3:
            raise RuntimeError("not yet")
        return {"nodes": [], "edges": []}

    with mock.patch.object(p2_mod, "_extract_batch", side_effect=fail_twice_then_succeed):
        results, _, _, _ = run_pass2_batched(
            files,
            schema,
            flat,
            MagicMock(),
            batch_token_target=100_000,
            batch_retry_max=2,
            max_workers=1,
        )

    assert len(extract_calls) == 3, (
        f"Expected 3 calls (1 initial + 2 retries) but got {len(extract_calls)}"
    )
    assert "a.md" in results
