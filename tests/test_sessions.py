"""Tests for the session-based run folder feature (Unit 3).

Covers:
- _make_session_dirs creates the three subdirectories (output, intermediate, input)
- _make_session_dirs returns a timestamp-shaped name
- _copy_input_files copies flat files (not subdirs)
- extract --help shows --session option
- extract with no flags auto-creates session and echoes name
- extract --session existing-name uses its dirs
- extract --session nonexistent raises error
- extract --session + --output-dir raises error
- input files are refreshed when --session is provided
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner


@pytest.fixture()
def input_dir(tmp_path):
    """A minimal input directory with one Markdown file."""
    d = tmp_path / "input"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# 1. _make_session_dirs creates the three subdirs
# ---------------------------------------------------------------------------


def test_make_session_dirs_creates_subdirs(tmp_path):
    from mykg.cli import _make_session_dirs

    name, out, inter = _make_session_dirs(tmp_path)

    assert (tmp_path / name / "output").is_dir()
    assert (tmp_path / name / "intermediate").is_dir()
    assert (tmp_path / name / "input").is_dir()
    assert out == tmp_path / name / "output"
    assert inter == tmp_path / name / "intermediate"


# ---------------------------------------------------------------------------
# 2. _make_session_dirs name is timestamp-shaped
# ---------------------------------------------------------------------------


def test_make_session_dirs_timestamp_format(tmp_path):
    from mykg.cli import _make_session_dirs

    name, _, _ = _make_session_dirs(tmp_path)

    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}$", name)


# ---------------------------------------------------------------------------
# 3. _copy_input_files copies files (not subdirs)
# ---------------------------------------------------------------------------


def test_copy_input_files_copies_flat(tmp_path):
    from mykg.cli import _copy_input_files

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("hello")
    (src / "b.md").write_text("world")
    (src / "subdir").mkdir()

    session = tmp_path / "sess"
    _copy_input_files(src, session)

    assert (session / "input" / "a.md").read_text() == "hello"
    assert (session / "input" / "b.md").read_text() == "world"
    assert not (session / "input" / "subdir").exists()


# ---------------------------------------------------------------------------
# 4. extract --help shows --session option
# ---------------------------------------------------------------------------


def test_extract_help_shows_session():
    from mykg.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["extract-graph", "--help"])

    assert "--session" in result.output


# ---------------------------------------------------------------------------
# 5. extract with no flags auto-creates session and echoes name
# ---------------------------------------------------------------------------


def test_extract_auto_creates_session(tmp_path, input_dir, monkeypatch):
    import mykg.cli as cli_mod
    import mykg.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(cli_mod, "run", lambda steps, ctx: None)
    monkeypatch.setattr(cli_mod, "load_adapter", lambda **kw: MagicMock())

    (input_dir / "doc.md").write_text("test")

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["extract-graph", str(input_dir)])

    assert result.exit_code == 0, result.output

    sessions = list((tmp_path / "sessions").iterdir())
    assert len(sessions) == 1

    sess = sessions[0]
    assert (sess / "intermediate").is_dir()
    assert (sess / "output").is_dir()
    assert (sess / "input" / "doc.md").exists()
    assert sess.name in result.output  # session name echoed to stdout
    assert (sess / "run.log").exists()  # log auto-placed in session folder


# ---------------------------------------------------------------------------
# 5b. extract with relative --log-file routes it into session folder
# ---------------------------------------------------------------------------


def test_extract_log_file_placed_in_session(tmp_path, input_dir, monkeypatch):
    import mykg.cli as cli_mod
    import mykg.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(cli_mod, "run", lambda steps, ctx: None)
    monkeypatch.setattr(cli_mod, "load_adapter", lambda **kw: MagicMock())

    (input_dir / "doc.md").write_text("test")

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["extract-graph", str(input_dir), "--log-file", "run.log"])

    assert result.exit_code == 0, result.output
    sess = list((tmp_path / "sessions").iterdir())[0]
    assert (sess / "run.log").exists()
    # log must NOT have been created in cwd
    assert not (tmp_path / "run.log").exists()


# ---------------------------------------------------------------------------
# 6. extract --session existing-name uses its dirs
# ---------------------------------------------------------------------------


def test_extract_session_uses_existing_dirs(tmp_path, input_dir, monkeypatch):
    import mykg.cli as cli_mod
    import mykg.config as cfg_mod

    sessions_root = tmp_path / "sessions"
    monkeypatch.setattr(cfg_mod, "SESSIONS_DIR", str(sessions_root))

    sess = sessions_root / "2026-01-01T00-00-00"
    (sess / "intermediate").mkdir(parents=True)
    (sess / "output").mkdir(parents=True)

    captured = {}

    def fake_run(steps, ctx):
        captured["output_dir"] = ctx.output_dir
        captured["intermediate_dir"] = ctx.intermediate_dir

    monkeypatch.setattr(cli_mod, "run", fake_run)
    monkeypatch.setattr(cli_mod, "load_adapter", lambda **kw: MagicMock())

    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        ["extract-graph", str(input_dir), "--session", "2026-01-01T00-00-00"],
    )

    assert result.exit_code == 0, result.output
    assert captured["output_dir"] == sess / "output"
    assert captured["intermediate_dir"] == sess / "intermediate"


# ---------------------------------------------------------------------------
# 7. extract --session nonexistent raises error
# ---------------------------------------------------------------------------


def test_extract_session_nonexistent_raises(tmp_path, input_dir, monkeypatch):
    import mykg.cli as cli_mod
    import mykg.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(cli_mod, "load_adapter", lambda **kw: MagicMock())

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["extract-graph", str(input_dir), "--session", "ghost"])

    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "error" in result.output.lower()


# ---------------------------------------------------------------------------
# 8. extract --session + --output-dir raises error
# ---------------------------------------------------------------------------


def test_extract_session_with_output_dir_raises(tmp_path, input_dir, monkeypatch):
    import mykg.cli as cli_mod
    import mykg.config as cfg_mod

    sessions_root = tmp_path / "sessions"
    monkeypatch.setattr(cfg_mod, "SESSIONS_DIR", str(sessions_root))

    sess = sessions_root / "existing"
    (sess / "intermediate").mkdir(parents=True)
    (sess / "output").mkdir(parents=True)

    monkeypatch.setattr(cli_mod, "load_adapter", lambda **kw: MagicMock())

    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        [
            "extract-graph",
            str(input_dir),
            "--session",
            "existing",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 9. input files are refreshed when --session is provided
# ---------------------------------------------------------------------------


def test_extract_session_refreshes_input_copy(tmp_path, input_dir, monkeypatch):
    import mykg.cli as cli_mod
    import mykg.config as cfg_mod

    sessions_root = tmp_path / "sessions"
    monkeypatch.setattr(cfg_mod, "SESSIONS_DIR", str(sessions_root))

    sess = sessions_root / "2026-01-01T00-00-00"
    (sess / "intermediate").mkdir(parents=True)
    (sess / "output").mkdir(parents=True)
    (sess / "input").mkdir(parents=True)

    monkeypatch.setattr(cli_mod, "run", lambda steps, ctx: None)
    monkeypatch.setattr(cli_mod, "load_adapter", lambda **kw: MagicMock())

    (input_dir / "new_doc.md").write_text("new content")

    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        ["extract-graph", str(input_dir), "--session", "2026-01-01T00-00-00"],
    )

    assert result.exit_code == 0, result.output
    assert (sess / "input" / "new_doc.md").exists()
