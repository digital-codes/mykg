from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from mykg.orchestrator import PipelineContext
from mykg.steps.step_preprocess import run_preprocess


def _make_ctx(tmp_path: Path) -> PipelineContext:
    input_dir = tmp_path / "input"
    intermediate_dir = tmp_path / "intermediate"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    intermediate_dir.mkdir()
    output_dir.mkdir()
    return PipelineContext(
        input_dir=input_dir,
        output_dir=output_dir,
        intermediate_dir=intermediate_dir,
        adapter=None,
    )


def test_preprocess_disabled_writes_sentinel(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    with (
        patch("mykg.config.PREPROCESS_ENABLED", False),
        patch("mykg.steps.step_preprocess.subprocess.run") as fake_run,
    ):
        run_preprocess(ctx)
    assert (ctx.intermediate_dir / "preprocess.done").exists()
    fake_run.assert_not_called()


def test_preprocess_no_non_md_files_skips(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    (ctx.input_dir / "a.md").write_text("# hi")
    with (
        patch("mykg.config.PREPROCESS_ENABLED", True),
        patch("mykg.steps.step_preprocess.subprocess.run") as fake_run,
    ):
        run_preprocess(ctx)
    assert (ctx.intermediate_dir / "preprocess.done").exists()
    fake_run.assert_not_called()


def test_preprocess_enabled_calls_parse_docs(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    (ctx.input_dir / "doc.pdf").write_bytes(b"%PDF-1.4 fake")
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    with (
        patch("mykg.config.PREPROCESS_ENABLED", True),
        patch("mykg.steps.step_preprocess.subprocess.run", side_effect=fake_run),
    ):
        run_preprocess(ctx)
    assert (ctx.intermediate_dir / "preprocess.done").exists()
    # Spawn shape: [sys.executable, "-m", "mykg", "parse-docs", ...]
    # — using the SAME interpreter avoids PATH shadowing by an older system mykg.
    assert captured["cmd"][:4] == [sys.executable, "-m", "mykg", "parse-docs"]
    assert "--input" in captured["cmd"]
    assert "--output" in captured["cmd"]


def test_preprocess_nonzero_raises(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    (ctx.input_dir / "doc.pdf").write_bytes(b"%PDF-1.4 fake")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1)

    with (
        patch("mykg.config.PREPROCESS_ENABLED", True),
        patch("mykg.steps.step_preprocess.subprocess.run", side_effect=fake_run),
    ):
        with pytest.raises(RuntimeError, match="exit code 1"):
            run_preprocess(ctx)


def test_preprocess_step_in_steps_registry() -> None:
    from mykg.pipeline import STEPS

    assert STEPS[0].name == "preprocess"
    assert STEPS[1].name == "ingest"
