from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from mykg.cli import cli


def _output(result) -> str:
    return (result.output or "") + str(result.exception or "")


def test_parse_docs_missing_mineru(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    runner = CliRunner()
    with patch("mykg.cli.shutil.which", return_value=None):
        result = runner.invoke(
            cli,
            ["parse-docs", "--input", str(input_dir), "--output", str(output_dir)],
        )
    assert result.exit_code != 0
    out = _output(result).lower()
    assert "mineru" in out
    assert "mykg[mineru]" in out


def test_parse_docs_builds_command(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    runner = CliRunner()
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    with (
        patch("mykg.cli.shutil.which", return_value="/usr/bin/mineru"),
        patch("mykg.cli.subprocess.run", side_effect=fake_run),
    ):
        result = runner.invoke(
            cli,
            ["parse-docs", "--input", str(input_dir), "--output", str(output_dir)],
        )
    assert result.exit_code == 0, _output(result)
    assert captured["cmd"][:2] == ["mineru", "-p"]
    assert "-i" in captured["cmd"]
    assert "-o" in captured["cmd"]
    assert str(input_dir) in captured["cmd"]
    assert str(output_dir) in captured["cmd"]
    assert output_dir.exists()


def test_parse_docs_pass_through_args(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    runner = CliRunner()
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    with (
        patch("mykg.cli.shutil.which", return_value="/usr/bin/mineru"),
        patch("mykg.cli.subprocess.run", side_effect=fake_run),
    ):
        result = runner.invoke(
            cli,
            [
                "parse-docs",
                "--input",
                str(input_dir),
                "--output",
                str(output_dir),
                "--backend",
                "pipeline",
            ],
        )
    assert result.exit_code == 0, _output(result)
    assert captured["cmd"][-2:] == ["--backend", "pipeline"]


def test_parse_docs_nonzero_exit(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    runner = CliRunner()

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 2)

    with (
        patch("mykg.cli.shutil.which", return_value="/usr/bin/mineru"),
        patch("mykg.cli.subprocess.run", side_effect=fake_run),
    ):
        result = runner.invoke(
            cli,
            ["parse-docs", "--input", str(input_dir), "--output", str(output_dir)],
        )
    assert result.exit_code != 0
    assert "2" in _output(result)
