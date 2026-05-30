from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from mykg import config as _cfg
from mykg.logging import get
from mykg.orchestrator import PipelineContext

log = get("mykg.steps.preprocess")


def _write_sentinel(intermediate_dir: Path, manifest: dict) -> None:
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    (intermediate_dir / "preprocess.done").write_text("done")
    (intermediate_dir / "preprocess_manifest.json").write_text(
        json.dumps(manifest, indent=_cfg.JSON_INDENT)
    )


def _discover_non_md_files(input_dir: Path, subdir: str) -> list[Path]:
    subdir_path = input_dir / subdir
    out: list[Path] = []
    for p in input_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() == ".md":
            continue
        if p == subdir_path or subdir_path in p.parents:
            continue
        out.append(p)
    return out


def run_preprocess(ctx: PipelineContext) -> None:
    if not _cfg.PREPROCESS_ENABLED:
        log.info("Step 0 — preprocess disabled in config; skipping")
        _write_sentinel(ctx.intermediate_dir, {"enabled": False})
        return

    non_md = _discover_non_md_files(ctx.input_dir, _cfg.PREPROCESS_SUBDIR)
    if not non_md:
        log.info("Step 0 — no non-md files to preprocess; skipping")
        _write_sentinel(
            ctx.intermediate_dir,
            {"enabled": True, "files_found": 0, "skipped": True},
        )
        return

    output_dir = ctx.input_dir / _cfg.PREPROCESS_SUBDIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use `python -m mykg` so the child runs the SAME interpreter/install as
    # the parent — bare `mykg` would resolve via PATH and could pick up an
    # older system-installed mykg (without parse-docs).
    cmd = [
        sys.executable,
        "-m",
        "mykg",
        "parse-docs",
        "--input",
        str(ctx.input_dir),
        "--output",
        str(output_dir),
        *_cfg.PREPROCESS_EXTRA_ARGS,
    ]
    log.info("Step 0 — running: %s", " ".join(cmd))

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            timeout=_cfg.PREPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"mykg parse-docs timed out after {_cfg.PREPROCESS_TIMEOUT_SECONDS}s"
        ) from exc
    duration = time.monotonic() - t0

    if proc.returncode != 0:
        raise RuntimeError(f"mykg parse-docs failed with exit code {proc.returncode}")

    log.info("Step 0 — preprocess complete in %.1fs (files_found=%d)", duration, len(non_md))
    _write_sentinel(
        ctx.intermediate_dir,
        {
            "enabled": True,
            "files_found": len(non_md),
            "duration_seconds": round(duration, 2),
            "returncode": proc.returncode,
            "subdir": _cfg.PREPROCESS_SUBDIR,
        },
    )
