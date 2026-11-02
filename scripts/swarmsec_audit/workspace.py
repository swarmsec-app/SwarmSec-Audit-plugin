"""Audit run directories: <project>/.swarmsec-audit/runs/<run-id>/."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

MODES = ("audit", "defi-audit", "attack-surface", "invariants", "verify", "diff-audit")
RUNS = Path(".swarmsec-audit") / "runs"


def now() -> datetime:
    """Current time, or SOURCE_DATE_EPOCH when set so reports can be reproduced byte for byte."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    return datetime.fromtimestamp(int(epoch), UTC) if epoch else datetime.now(UTC)


def git(project_root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), *args],
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def revision(project_root: Path) -> dict:
    commit = git(project_root, "rev-parse", "HEAD")
    if commit is None:
        return {"commit": None, "dirty": None}
    status = git(project_root, "status", "--porcelain", "--", ".", ":(exclude).swarmsec-audit")
    return {"commit": commit, "dirty": bool(status)}


def create_run(project_root: Path, target: str, mode: str, diff_range: str | None, build: dict, tools: dict) -> Path:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    runs = project_root / RUNS
    run_id = now().strftime("%Y%m%dT%H%M%SZ")
    run_dir = runs / run_id
    suffix = 1
    while run_dir.exists():
        suffix += 1
        run_dir = runs / f"{run_id}-{suffix}"
    (run_dir / "findings").mkdir(parents=True)
    (run_dir / "tool-runs").mkdir()
    run = {
        "schema_version": "1.0",
        "run_id": run_dir.name,
        "created_at": now().isoformat(timespec="seconds"),
        "project_root": project_root.resolve().as_posix(),
        "target": target,
        "mode": mode,
        "diff_range": diff_range,
        "revision": revision(project_root),
        "build": {"system": build.get("system"), "compiler": build.get("compiler"), "status": "not-attempted"},
        "tools": tools,
        "scope": {"included": [target], "excluded": []},
        "coverage_gaps": [],
        "limitations": [],
    }
    write_json(run_dir / "run.json", run)
    return run_dir


def resolve_run_dir(path: Path) -> Path:
    """Accept a run directory, the runs/ folder, a project root, or a path ending in 'latest'."""
    path = path.resolve()
    if (path / "run.json").is_file():
        return path
    if path.name == "latest":
        path = path.parent
    for candidate in (path, path / RUNS):
        if candidate.is_dir():
            runs = sorted(p for p in candidate.iterdir() if (p / "run.json").is_file())
            if runs:
                return runs[-1]
    raise FileNotFoundError(f"no audit run found at {path}")


def expand_latest(path: Path) -> Path:
    """Replace a 'latest' path segment, e.g. runs/latest/findings/SWARM-001.json, with the newest run."""
    parts = path.parts
    if path.exists() or "latest" not in parts:
        return path
    i = parts.index("latest")
    return resolve_run_dir(Path(*parts[: i + 1])).joinpath(*parts[i + 1 :])


def load_run(run_dir: Path) -> dict:
    return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
